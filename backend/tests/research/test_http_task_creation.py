"""Contract tests for depth, durable idempotency and the configured browser origin."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.accounts import Store
from backend.app1 import create_app
from backend.config import Settings
from backend.research.api import attach
from backend.research.schemas import Budget, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus
from backend.tests.research.test_execution import account_rows, until


class StagedCorpus(LocalCorpus):
    """Return evidence for the current missing slot on successive focused queries."""

    def discover(self, req, owner, scope):
        if req.query.endswith("dataset"):
            return ["dataset"]
        if req.query.endswith("precision"):
            return ["metric"]
        return ["method"]


def task_api(tmp_path, corpus_factory):
    app = FastAPI()
    accounts = Store(str(tmp_path / "identity"))
    account_rows(accounts)
    worker = attach(app, Settings(runtime_dir=str(tmp_path / "tasks")), accounts, corpus_factory)
    return TestClient(app), worker


def test_http_depth_controls_how_many_gaps_can_be_explored(tmp_path, monkeypatch):
    monkeypatch.delenv("SCHOLARLENS_APPROVED_REGISTRY", raising=False)
    goal = "Atlas method dataset and metric"
    source = StagedCorpus(
        [
            {"paper_id": "method", "title": "Atlas", "abstract": "Atlas uses a lexical method."},
            {"paper_id": "dataset", "title": "Atlas", "abstract": "The Atlas dataset has images."},
            {"paper_id": "metric", "title": "Atlas", "abstract": "Atlas precision was 0.82."},
        ],
        "depth-fixture",
    )
    client, worker = task_api(tmp_path, lambda scope: source)
    with client:
        ids = []
        for key, body in (("standard", {"goal": goal}), ("deep", {"goal": goal, "depth": "deep"})):
            result = client.post("/api/research/tasks", headers={"Idempotency-Key": key}, json=body)
            assert result.status_code == 202
            ids.append(result.json()["task_id"])
        budgets = [
            client.get("/api/research/tasks/" + uid).json()["state"]["budget"] for uid in ids
        ]
        assert [
            (
                b["max_rounds"],
                b["max_tool_calls"],
                b["max_evidence"],
                b["max_duration_seconds"],
                b["max_model_calls"],
            )
            for b in budgets
        ] == [(2, 16, 12, 180, 0), (4, 30, 30, 600, 0)]
        worker.start()
        try:
            finals = [
                until(
                    lambda: worker.store.get(1, uid)[0],
                    lambda state: state.status in {"partial", "completed"},
                )
                for uid in ids
            ]
        finally:
            worker.close()
    assert [(s.status, s.stop_reason, s.budget.rounds_used) for s in finals] == [
        ("partial", "budget", 2),
        ("completed", "complete", 3),
    ]
    assert [s.budget.model_calls_used for s in finals] == [0, 0]
    assert [{r.paper_id for r in s.evidence_refs} for s in finals] == [
        {"method", "dataset"},
        {"method", "dataset", "metric"},
    ]


def test_replay_while_corpus_unavailable_reuses_task_in_owners_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("SCHOLARLENS_APPROVED_REGISTRY", raising=False)
    generations = []

    def get_source(scope):
        generations.append(1)
        if len(generations) > 1:
            raise OSError("offline corpus")
        return SimpleNamespace(generation="original")

    client, worker = task_api(tmp_path, get_source)
    body = {"goal": "Check the local study", "mode": "personal_model"}
    headers = {"Idempotency-Key": "same"}
    try:
        with client:
            first = client.post("/api/research/tasks", json=body, headers=headers)
            assert first.status_code == 202
            worker._execute(1, first.json()["task_id"])
            replay = client.post("/api/research/tasks", json=body, headers=headers)
            assert replay.status_code == 202
            assert replay.json() == {
                **first.json(),
                "status": "awaiting_credentials",
                "revision": 1,
            }
            conflict = client.post(
                "/api/research/tasks", json={**body, "depth": "deep"}, headers=headers
            )
            assert conflict.status_code == 409
            assert len(generations) == 1
            other = client.post(
                "/api/research/tasks", json=body, headers={**headers, "Authorization": "second"}
            )
            new = client.post(
                "/api/research/tasks", json=body, headers={"Idempotency-Key": "another"}
            )
            assert (other.status_code, new.status_code) == (503, 503)
            assert worker.store.list_tasks(2) == []
            assert len(worker.store.list_tasks(1)) == 1
    finally:
        worker.close()


def test_personal_model_limits_survive_pause_and_http_resume(tmp_path, monkeypatch):
    monkeypatch.delenv("SCHOLARLENS_APPROVED_REGISTRY", raising=False)
    client, worker = task_api(tmp_path, lambda scope: SimpleNamespace(generation="fixed"))
    try:
        with client:
            settings = {
                "X-ScholarLens-AI-URL": "https://example.org/v1",
                "X-ScholarLens-AI-Model": "fixture",
                "X-ScholarLens-AI-Key": "local-sentinel",
            }
            for depth, model_calls in (("standard", 2), ("deep", 4)):
                res = client.post(
                    "/api/research/tasks",
                    json={"goal": "Study local data", "depth": depth, "mode": "personal_model"},
                    headers={**settings, "Idempotency-Key": depth},
                )
                assert res.status_code == 202
                tid = res.json()["task_id"]
                state, rev = worker.store.get(1, tid)
                assert state.budget.max_model_calls == model_calls
                state.status = "running"
                state.budget.tool_calls_used = 1
                state.budget.deadline = datetime.now(timezone.utc) + timedelta(seconds=30)
                rev = worker.store.save(1, state, rev, "started", "initial-progress")
                state.status = "paused"
                worker.store.save(1, state, rev, "paused", "fixture-pause")
                resume = client.post(f"/api/research/tasks/{tid}/resume", headers=settings)
                assert resume.status_code == 202
                actual = worker.store.get(1, tid)[0]
                assert actual.status == "queued" and actual.budget == state.budget
    finally:
        worker.close()


def test_store_default_remains_available_to_controlled_offline_runs(tmp_path):
    store = ResearchStore(tmp_path)
    state, rev, _ = store.create(1, "offline", TaskInput(goal="offline baseline"), "fixed")
    assert rev == 0 and state.budget == Budget()


def test_cors_preflight_for_research_uses_only_configured_origin_and_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLARLENS_RESEARCH_ENABLED", "true")
    origin = "https://frontend.example"
    app = create_app(
        Settings(cors_origins=origin, runtime_dir=str(tmp_path)), client=SimpleNamespace()
    )
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type,idempotency-key,x-scholarlens-ai-url,"
        "x-scholarlens-ai-model,x-scholarlens-ai-key,x-scholarlens-ai-token-parameter,x-scholarlens-ai-protocol",
    }
    with TestClient(app) as client:
        allowed = client.options("/api/research/tasks", headers=headers)
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == origin
        requested = set(headers["Access-Control-Request-Headers"].split(","))
        allowed_names = {
            s.strip().lower() for s in allowed.headers["access-control-allow-headers"].split(",")
        }
        assert requested <= allowed_names
        unlisted = client.options(
            "/api/research/tasks", headers={**headers, "Origin": "https://other.example"}
        )
        assert unlisted.status_code == 400 and "access-control-allow-origin" not in unlisted.headers
        unknown_header = client.options(
            "/api/research/tasks",
            headers={**headers, "Access-Control-Request-Headers": "x-unconfigured-header"},
        )
        assert unknown_header.status_code == 400


def test_report_artifacts_become_readable_after_publication(tmp_path, monkeypatch):
    monkeypatch.delenv("SCHOLARLENS_APPROVED_REGISTRY", raising=False)
    client, worker = task_api(tmp_path, lambda scope: SimpleNamespace(generation="known"))
    try:
        with client:
            created = client.post(
                "/api/research/tasks",
                headers={"Idempotency-Key": "artifact"},
                json={"goal": "Read verified local report"},
            )
            assert created.status_code == 202
            tid = created.json()["task_id"]
            url = "/api/research/tasks/" + tid
            report = worker.store.put_artifact(1, tid, "report", b'{"summary":"verified"}', "known")
            markdown = worker.store.put_artifact(1, tid, "markdown", b"# Reviewed", "known")
            for aid in (report, markdown):
                assert client.get(f"{url}/artifacts/{aid}").status_code == 404
            assert client.get(f"{url}/report").status_code == 409
            state, rev = worker.store.get(1, tid)
            state.status = "running"
            rev = worker.store.save(1, state, rev, "started", "start")
            state.status = "completed"
            state.artifact_refs.extend([report, markdown])
            worker.store.save(1, state, rev, "completed", "publish")
            assert client.get(f"{url}/report").json() == {"summary": "verified"}
            assert client.get(f"{url}/artifacts/{report}").json() == {"summary": "verified"}
            assert client.get(f"{url}/artifacts/{markdown}").text == "# Reviewed"
            for aid in (report, markdown):
                denied = client.get(f"{url}/artifacts/{aid}", headers={"Authorization": "second"})
                assert denied.status_code == 404
    finally:
        worker.close()
