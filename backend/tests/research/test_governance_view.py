"""Exercise the deployed app factory and the same registry format used by the worker."""

from contextlib import closing
from hashlib import sha256
import logging
import secrets

from fastapi.testclient import TestClient

from backend.accounts import Store
from backend.config import Settings
from backend.research.governance import registry_view
from backend.research.lab_store import LabStore
from backend.research.skills.registry import POLICY_BASE, SKILL_BASE
from backend.research.skills.releases import ProgramReceipt
from tools.research_evolution.program_release import registry_db, transition


def login(client, name):
    data = {"username": name, "password": secrets.token_urlsafe(24)}
    user = client.post("/api/auth/register", json=data)
    assert user.status_code == 201
    response = client.post("/api/auth/login", json=data)
    assert response.status_code == 200
    return user.json()["id"], {"Authorization": "Bearer " + response.json()["access_token"]}


def test_product_roles_no_store_log_and_no_writes(tmp_path, monkeypatch, caplog):
    runtime = tmp_path / "runtime"
    lab = tmp_path / "lab.sqlite3"
    monkeypatch.setenv("SCHOLARLENS_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("SCHOLARLENS_RESEARCH_ENABLED", "false")
    monkeypatch.setenv("SCHOLARLENS_EVOLUTION_LAB", "true")
    monkeypatch.setenv("SCHOLARLENS_LAB_DB", str(lab))
    monkeypatch.delenv("SCHOLARLENS_APPROVED_REGISTRY", raising=False)
    from backend.app1 import create_app

    settings = Settings(runtime_dir=str(runtime))
    app = create_app(settings, client=object())
    prefix = "/api/evolution-lab/"
    audit = "uvicorn.error.scholarlens_governance"
    caplog.set_level(logging.INFO, logger=audit)
    with TestClient(app) as client:
        member_id, member = login(client, "gov-member")
        admin_id, admin = login(client, "gov-admin")
        accounts = Store(str(runtime))
        with accounts.connect() as db:
            db.execute("UPDATE users SET role='admin' WHERE id=?", (admin_id,))
        compare = {"split": "independent", "task": "fixture", "left": "contract", "right": "skill"}
        for route, params in [("governance", {}), ("index", {}), ("compare", compare)]:
            for headers, expected in [({}, 401), (member, 403)]:
                response = client.get(prefix + route, headers=headers, params=params)
                assert response.status_code == expected and "no-store" in response.headers["Cache-Control"]
        response = client.get(prefix + "governance", headers=admin)
        assert response.status_code == 200 and "no-store" in response.headers["Cache-Control"]
        info = response.json()
        assert info["registry"]["status"] == "builtin"
        assert "search_papers" in info["tools"]
        assert set(info["model"]) == {"protocols", "capacity_scope", "global_concurrency", "per_host_concurrency"}
        assert client.get(prefix + "index", headers=admin).status_code == 503
        assert not lab.exists()
        LabStore(lab, writable=True)
        before = sha256(lab.read_bytes()).digest()
        assert client.get(prefix + "index", headers=admin).json()["runs"] == []
        assert client.get(prefix + "compare", headers=admin, params=compare).status_code == 404
        for route in ("governance", "index", "compare"):
            assert set(app.openapi()["paths"][prefix + route]) == {"get"}
            assert client.post(prefix + route, headers=admin).status_code == 405
        assert sha256(lab.read_bytes()).digest() == before
        with accounts.connect() as db:
            db.execute("UPDATE users SET role='user' WHERE id=?", (admin_id,))
        assert client.get(prefix + "governance", headers=admin).status_code == 403
    logs = [r.getMessage() for r in caplog.records if r.name == audit]
    assert f"research_governance action=governance method=GET status=403 account={member_id}" in logs
    assert f"research_governance action=governance method=GET status=200 account={admin_id}" in logs
    assert f"research_governance action=governance method=GET status=403 account={admin_id}" in logs
    assert "research_governance action=governance method=GET status=401 account=unresolved" in logs
    assert all("Bearer" not in row and "gov-admin" not in row and "fixture" not in row for row in logs)
    monkeypatch.setenv("SCHOLARLENS_EVOLUTION_LAB", "false")
    with TestClient(create_app(settings, client=object())) as client:
        assert client.get(prefix + "governance").status_code == 404


def test_version_metadata_receipt_rollback_history_and_integrity(tmp_path):
    directory = tmp_path / "registry"
    assert registry_view(directory)["status"] == "unavailable" and not directory.exists()
    receipt = ProgramReceipt.model_validate({
        "program": {"intents": ["comparison"], "min_papers": 2, "steps": ["identify_comparators"],
                    "expected": "condition_matrix", "dataset_hash": "1" * 64, "trace_hashes": ["2" * 64]},
        "base_skill": SKILL_BASE, "base_policy": POLICY_BASE, "lab_candidate": "3" * 64,
        "review": "4" * 64, "regression": "5" * 64, "suite": "6" * 64, "parent": SKILL_BASE,
    })
    with closing(registry_db(directory)) as db, db:
        db.execute("INSERT INTO approved VALUES('program',?,?,?,?)",
                   (receipt.version, receipt.encoded(), receipt.parent, receipt.review))
        db.execute("INSERT INTO active VALUES('program',?)", (receipt.version,))
    # An active pointer without an approval must not appear as a valid release.
    assert registry_view(directory)["status"] == "unavailable"
    with closing(registry_db(directory)) as db, db:
        db.execute("INSERT INTO audit(kind,version,action,reviewer,evaluation) "
                   "VALUES('program',?,'publish_program','fixture-reviewer',?)", (receipt.version, receipt.regression))
    path = directory / "approved.sqlite3"
    before = sha256(path.read_bytes()).digest()
    view = registry_view(directory)
    assert view["program"] == receipt.version
    assert view["program_basis"] == {"skill": SKILL_BASE, "policy": POLICY_BASE}
    assert view["history"] == [{"seq": 1, "kind": "program", "version": receipt.version, "action": "publish_program"}]
    assert sha256(path.read_bytes()).digest() == before
    transition(directory, "fixture-reviewer", receipt.version)
    after = registry_view(directory)
    assert after["status"] == "configured" and after["program"] is None and after["program_basis"] is None
    assert [row["action"] for row in after["history"]] == ["rollback_program", "publish_program"]
