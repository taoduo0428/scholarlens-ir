"""Regression checks for Compose SCHOLARLENS_PRA_ARM pass-through and A/G/R switching."""

from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
import yaml

from tools.research_demo import create_demo


ROOT = Path(__file__).resolve().parents[3]


def _register_and_auth(client: TestClient) -> dict[str, str]:
    credentials = {"username": f"arm-{uuid4().hex[:10]}", "password": uuid4().hex}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    token = client.post("/api/auth/login", json=credentials).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _run_task(client: TestClient, headers: dict[str, str], goal: str) -> dict:
    created = client.post(
        "/api/research/tasks",
        headers={**headers, "Idempotency-Key": uuid4().hex},
        json={"goal": goal, "scope": {"paper_ids": ["ui:lens", "ui:wave"]}},
    )
    assert created.status_code == 202, created.text
    tid = created.json()["task_id"]
    deadline = monotonic() + 20
    while monotonic() < deadline:
        detail = client.get(f"/api/research/tasks/{tid}", headers=headers).json()
        if detail["state"]["status"] in {"completed", "partial"} and not client.app.state.research_worker.active:
            return detail
        sleep(0.05)
    pytest.fail(f"Task {tid} did not finish within timeout")


def test_product_compose_passes_scholarlens_pra_arm_default_a():
    compose = yaml.safe_load((ROOT / "infra" / "product.compose.yml").read_text(encoding="utf-8"))
    api_env = compose["services"]["api"]["environment"]
    assert api_env["SCHOLARLENS_PRA_ARM"] == "${SCHOLARLENS_PRA_ARM:-A}"
    env_example = (ROOT / "infra" / ".env.example").read_text(encoding="utf-8")
    assert "SCHOLARLENS_PRA_ARM=A" in env_example


def test_pra_arm_runtime_switch_a_g_r_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLARLENS_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("SCHOLARLENS_E11_ENABLED", "true")
    monkeypatch.delenv("SCHOLARLENS_PRA_ARM", raising=False)

    app = create_demo(tmp_path, "", "profile-fixture")
    recorded_ids: list[tuple[str, str]] = []
    with TestClient(app) as client:
        headers = _register_and_auth(client)

        default_detail = _run_task(client, headers, "Default A: summarize optical lens measurements.")
        assert default_detail["state"]["retrieval_policy"] == "E11"
        assert default_detail["state"]["pra_arm"] == "A"
        recorded_ids.append((default_detail["state"]["run_id"], "A"))

        for arm in ("G", "R"):
            monkeypatch.setenv("SCHOLARLENS_PRA_ARM", arm)
            detail = _run_task(client, headers, f"Arm {arm}: compare lens and wave methods.")
            assert detail["state"]["retrieval_policy"] == "E11"
            assert detail["state"]["pra_arm"] == arm
            recorded_ids.append((detail["state"]["run_id"], arm))

        monkeypatch.setenv("SCHOLARLENS_PRA_ARM", "INVALID_ARM")
        bad = client.post(
            "/api/research/tasks",
            headers={**headers, "Idempotency-Key": uuid4().hex},
            json={"goal": "Invalid arm check.", "scope": {"paper_ids": ["ui:lens"]}},
        )
        assert bad.status_code == 503
        assert bad.json()["error"]["code"] == "research_policy_unavailable"

        monkeypatch.delenv("SCHOLARLENS_PRA_ARM", raising=False)
        rollback_detail = _run_task(client, headers, "Rollback A: verify default restored.")
        assert rollback_detail["state"]["retrieval_policy"] == "E11"
        assert rollback_detail["state"]["pra_arm"] == "A"
        recorded_ids.append((rollback_detail["state"]["run_id"], "A"))

        for tid, expected_arm in recorded_ids:
            saved = client.get(f"/api/research/tasks/{tid}", headers=headers)
            assert saved.status_code == 200
            assert saved.json()["state"]["pra_arm"] == expected_arm
