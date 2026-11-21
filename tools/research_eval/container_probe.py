"""Exercise two application images against a disposable Compose project.

Pass this file on standard input to the API container's python interpreter.
The test requires a dedicated empty volume, a specifically named fixture
index, and an explicitly selected stage. Credentials stay in the fixture.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.research.store import ResearchStore


ROOT = Path("/var/lib/scholarlens")
MARKER = ROOT / ".container-rehearsal.json"
API = "http://127.0.0.1:8000"
INDEX = "scholarlens-fixture"


def request(url, data=None, headers=None, method=None, expected=200):
    body = None if data is None else json.dumps(data).encode()
    req = Request(url, data=body, method=method,
                  headers={"Content-Type": "application/json", **(headers or {})})
    try:
        response = urlopen(req, timeout=12)
    except HTTPError as error:
        response = error
    with response:
        if response.status != expected:
            raise ValueError(f"{req.method if method else req.get_method()} {req.selector} returned {response.status}, expected {expected}")
        raw = response.read()
        return json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw


def signed(credentials):
    token = request(API + "/api/auth/login", credentials)["access_token"]
    return {"Authorization": "Bearer " + token}


def digest(report):
    return hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()


def initialize():
    if MARKER.exists():
        raise RuntimeError("fixture already initialized")
    es = "http://search:9200/"
    with urlopen(es + "_cat/indices?format=json") as response:
        if json.load(response):
            raise RuntimeError("empty search fixture required")
    assert request(API + "/readyz", expected=503)["status"] == "unavailable"
    request(es + INDEX + "-v1", {"mappings": {"_meta": {"data_status": "mock", "input_records": 1},
            "properties": {"paper_id": {"type": "keyword"}, "title": {"type": "text"},
                           "abstract": {"type": "text"}}}, "aliases": {INDEX: {}}}, method="PUT")
    request(es + INDEX + "/_doc/demo?refresh=true", {"paper_id": "demo", "title": "Mirror Test",
            "abstract": "We developed a mirror tracker for optical alignment."}, method="PUT", expected=201)
    assert request(API + "/readyz")["status"] == "ready"
    accounts = [{"username": "fixture-" + secrets.token_hex(5), "password": secrets.token_urlsafe(24)}
                for _ in range(2)]
    for credentials in accounts:
        request(API + "/api/auth/register", credentials, expected=201)
    headers = {**signed(accounts[0]), "Idempotency-Key": "container-rehearsal"}
    task = request(API + "/api/research/tasks", {"goal": 'Quote the opening sentence of "Mirror Test".',
                   "scope": {"paper_ids": ["demo"]}}, headers, expected=202)
    url = API + "/api/research/tasks/" + task["task_id"]
    for _ in range(100):
        if request(url, headers=headers)["state"]["status"] in {"partial", "completed"}:
            break
        time.sleep(0.5)
    report = request(url + "/report", headers=headers)
    assert report["sections"]["verified"]
    ResearchStore(ROOT).backup(ROOT / "fixture-snapshot.sqlite3")
    with MARKER.open("x", encoding="utf8") as marker:
        os.chmod(MARKER, 0o600)
        json.dump({"accounts": accounts, "task": task["task_id"], "report_hash": digest(report)}, marker)


def verify(stage):
    marker = json.loads(MARKER.read_bytes())
    assert request(API + "/healthz")["status"] == "alive"
    assert request(API + "/readyz")["status"] == "ready"
    assert b'<div id="root">' in request(API + "/")
    headers, other = (signed(account) for account in marker["accounts"])
    url = API + "/api/research/tasks/" + marker["task"] + "/report"
    report = request(url, headers=headers)
    assert digest(report) == marker["report_hash"]
    request(url, headers=other, expected=404)
    destination = tempfile.mkdtemp(prefix="restore-" + stage + "-", dir=ROOT)
    restored = ResearchStore.restore(ROOT / "fixture-snapshot.sqlite3", destination)
    with restored._db() as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        owner, = connection.execute("SELECT owner FROM tasks WHERE id=?", (marker["task"],)).fetchone()
    state, _ = restored.get(owner, marker["task"])
    aid = next(ref for ref in state.artifact_refs if ref.startswith("report-"))
    assert digest(json.loads(restored.artifact(owner, marker["task"], aid)["content"])) == marker["report_hash"]
    return {"stage": stage, "uid": os.getuid(), "health": 200, "ready": 200, "frontend": 200,
            "other_owner_report": 404, "report_restored": True, "verified_claims": len(report["sections"]["verified"])}


if __name__ == "__main__":
    stage, = sys.argv[1:]
    if (stage not in {"initialize", "upgrade", "rollback"} or os.getuid() != 10001
            or os.environ.get("ELASTICSEARCH_INDEX") != INDEX
            or os.environ.get("SCHOLARLENS_RUNTIME_DIR") != str(ROOT)):
        raise RuntimeError("dedicated fixture required")
    if stage == "initialize":
        initialize()
    print(json.dumps(verify(stage)))
