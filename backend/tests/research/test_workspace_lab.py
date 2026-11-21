import secrets

import pytest
from fastapi.testclient import TestClient

from backend.accounts import Store
from backend.research.lab_store import LabStore, fingerprint
from tools.research_demo import create_demo


def account(client, name):
    data = {"username": name, "password": secrets.token_urlsafe(20)}
    assert client.post("/api/auth/register", json=data).status_code == 201
    return {
        "Authorization": "Bearer "
        + client.post("/api/auth/login", json=data).json()["access_token"]
    }


def trial(i, v, policy):
    return dict(
        split="independent",
        task=f"task-{i}",
        variant=v,
        scope=["a"],
        goal="q",
        suite="suite",
        generation="g",
        origin="frozen-public-replay",
        max_tools=10,
        max_models=0,
        model="none",
        source_ids=["c"],
        source_checks=[True],
        exact_answer=True,
        abstained=None,
        policy=fingerprint(policy),
        scope_errors=0,
        private_sources=0,
    )


def test_real_account_lab_read_only_and_flags(tmp_path, monkeypatch):
    path = tmp_path / "lab.sqlite3"
    lab = LabStore(path, writable=True)
    for v in ["contract", "harness"]:
        lab.save_trial(trial(1, v, {}))
    monkeypatch.setenv("SCHOLARLENS_EVOLUTION_LAB", "true")
    monkeypatch.setenv("SCHOLARLENS_LAB_DB", str(path))
    runtime = tmp_path / "runtime"
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<html><body>isolated lab test</body></html>")
    with TestClient(create_demo(runtime, tmp_path / "web", "fixture")) as c:
        a = account(c, "viewer-user")
        b = account(c, "operator-user")
        with Store(str(runtime)).connect() as db:
            db.execute("UPDATE users SET role='admin' WHERE username='operator-user'")
        url = "/api/evolution-lab"
        assert c.get(url + "/index").status_code == 401
        assert c.get(url + "/index", headers=a).status_code == 403
        assert c.get(url + "/index", headers=b).status_code == 200
        params = dict(split="independent", task="task-1", left="contract", right="harness")
        assert c.get(url + "/compare", params=params, headers=b).json()["matched_model"]
        assert c.get(url + "/compare", params=params, headers=a).status_code == 403
        assert c.post(url + "/compare", json=params, headers=b).status_code == 405
    monkeypatch.delenv("SCHOLARLENS_EVOLUTION_LAB")
    app = create_demo(tmp_path / "off", tmp_path / "web", "fixture")
    with TestClient(app) as c:
        assert c.get("/api/evolution-lab/index").status_code == 404
        assert not any("/evolution-lab" in route for route in app.openapi()["paths"])


@pytest.mark.parametrize("gain", [True, False])
def test_registry_independent_review_and_rollback(tmp_path, gain):
    policy = {"suite": "suite"}
    lab = LabStore(tmp_path / "lab", writable=True)
    marks = {}
    for i in range(14):
        for v in ("contract", "harness"):
            lab.save_trial(trial(i, v, policy))
        marks[f"task-{i}"] = {
            "base": False,
            "candidate": gain,
            "source_note": "synthetic lifecycle test",
        }
    review = {"reviewer": "fixture operator", "tasks": marks, "policy": fingerprint(policy)}
    version = lab.register(policy, review=review)
    if gain:
        lab.operator(version, "approve", "fixture reviewer")
        lab.operator(version, "rollback", "fixture reviewer")
        assert lab.index()["versions"][0]["decision"] == "rolled_back"
    else:
        with pytest.raises(ValueError):
            lab.operator(version, "approve", "fixture reviewer")


def test_registry_rejects_unverified_registration_and_private_trace(tmp_path):
    lab = LabStore(tmp_path / "lab", writable=True)
    with pytest.raises(ValueError):
        lab.save_trial({**trial(1, "contract", {}), "private_sources": 1})
    version = lab.register({}, [])
    with pytest.raises(ValueError):
        lab.operator(version, "approve", "local operator")
