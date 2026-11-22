from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import sqlite3
from time import monotonic, sleep
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient
from filelock import FileLock
import pytest

from backend.research.lifecycle import erase_terminal
from backend.research.schemas import TaskInput
from backend.research.store import Conflict, NotFound, ResearchStore, digest
from tools.research_demo import create_demo
from tools.research_retention import retention_batch


def user(client):
    credentials = {"username": "acct-" + uuid4().hex, "password": uuid4().hex}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    token = client.post("/api/auth/login", json=credentials).json()["access_token"]
    return {"Authorization": "Bearer " + token, "Idempotency-Key": uuid4().hex}


def test_export_and_erase_via_authenticated_task(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLARLENS_E11_ENABLED", "true")
    app = create_demo(tmp_path, "", "profile-fixture")
    with TestClient(app) as client:
        owner, other = user(client), user(client)
        task = {"goal": "综合两篇论文的方法。", "scope": {"paper_ids": ["ui:lens", "ui:wave"]}}
        created = client.post("/api/research/tasks", json=task, headers=owner)
        assert created.status_code == 202
        uid = created.json()["task_id"]
        path = "/api/research/tasks/" + uid
        deadline = monotonic() + 20
        while monotonic() < deadline:
            result = client.get(path, headers=owner).json()
            if result["state"]["status"] in {"completed", "partial"} and not app.state.research_worker.active:
                break
            sleep(.05)
        else:
            pytest.fail("task did not finish")
        delete_url = path + "?revision=" + str(result["revision"])
        assert client.get(path + "/export", headers=other).status_code == 404
        assert client.delete(delete_url, headers=other).status_code == 404
        assert client.delete(path + "?revision=0", headers=owner).status_code == 409
        response = client.get(path + "/export", headers=owner)
        assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
        with ZipFile(BytesIO(response.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert (manifest["task_id"], manifest["revision"]) == (uid, result["revision"])
            assert json.loads(archive.read("state.json")) == result["state"]
            assert {entry["path"] for entry in manifest["files"]} == set(archive.namelist()) - {"manifest.json"}
            assert any(name.startswith("artifacts/markdown-") for name in archive.namelist())
            for entry in manifest["files"]:
                data = archive.read(entry["path"])
                assert (len(data), digest(data)) == (entry["bytes"], entry["sha256"])
        graph = tmp_path / "research-graph.sqlite3"
        store = ResearchStore(tmp_path)
        with store._db(write=True) as db:
            aid = result["state"]["artifact_refs"][0]
            original = db.execute("SELECT content FROM artifacts WHERE task=? AND id=?", (uid, aid)).fetchone()[0]
            db.execute("UPDATE artifacts SET content=? WHERE task=? AND id=?", (b"damaged", uid, aid))
        failure = client.get(path + "/export", headers=owner)
        assert failure.status_code == 409 and failure.json()["error"]["code"] == "artifact_integrity"
        with store._db(write=True) as db:
            db.execute("UPDATE artifacts SET content=? WHERE task=? AND id=?", (original, uid, aid))
        with sqlite3.connect(graph) as db:
            assert db.execute("SELECT count(*) FROM checkpoints WHERE thread_id=?", (uid,)).fetchone()[0] > 0
        assert client.delete(delete_url, headers=owner).status_code == 204
        for endpoint in ("", "/export", "/events", "/report"):
            assert client.get(path + endpoint, headers=owner).status_code == 404
        with sqlite3.connect(graph) as db:
            for table in ("writes", "checkpoints"):
                assert db.execute(f"SELECT count(*) FROM {table} WHERE thread_id=?", (uid,)).fetchone()[0] == 0


def test_retention_scope_stale_preview_and_graph_failure(tmp_path):
    store = ResearchStore(tmp_path)
    ids = [str(store.create(owner, str(i), TaskInput(goal="Find a reported result."), "seed")[0].run_id)
           for i, owner in enumerate((7, 7, 8, 7))]
    with store._db(write=True) as db:
        db.execute("UPDATE tasks SET updated_at='2001-01-01T00:00:00+00:00',status='failed' WHERE id IN (?,?,?)", ids[:3])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    preview = retention_batch(tmp_path, 7, cutoff)
    assert (preview["selected"], preview["deleted"]) == (2, 0)
    with pytest.raises(RuntimeError, match="worker_active"), FileLock(str(store.path.with_suffix(".worker.lock"))):
        retention_batch(tmp_path, 7, cutoff, confirm=preview["preview_sha256"])
    with pytest.raises(ValueError, match="preview_changed"):
        retention_batch(tmp_path, 8, cutoff, confirm=preview["preview_sha256"])
    with pytest.raises(Conflict):
        erase_terminal(store, 7, ids[3], 0)
    with pytest.raises(NotFound):
        erase_terminal(store, 7, ids[2], 0)
    graph = tmp_path / "research-graph.sqlite3"
    with sqlite3.connect(graph) as db:
        db.execute("CREATE TABLE future_schema(v TEXT)")
    with pytest.raises(Conflict, match="graph_schema_unavailable"):
        erase_terminal(store, 7, ids[0], 0)
    assert retention_batch(tmp_path, 7, cutoff) == preview
    with sqlite3.connect(graph) as db:
        db.execute("DROP TABLE future_schema")
    assert retention_batch(tmp_path, 7, cutoff, confirm=preview["preview_sha256"])["deleted"] == 2
    assert [r["id"] for r in store.list_tasks(7)] == [ids[3]]
    assert [r["id"] for r in store.list_tasks(8)] == [ids[2]]
