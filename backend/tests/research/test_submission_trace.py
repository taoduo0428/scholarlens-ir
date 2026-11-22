from time import monotonic, sleep
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.research.schemas import TaskInput
from backend.research.store import NotFound, ResearchStore
from tools.research_demo import create_demo


def test_additive_table_and_atomic_scope(tmp_path):
    store = ResearchStore(tmp_path)
    body = TaskInput(goal="Find the opening sentence.")
    old, *_ = store.create(1, "old", body, "demo")
    with store._db(write=True) as db:
        db.execute("DROP TABLE submission_trace")
    store = ResearchStore(tmp_path)
    assert store.submission_trace(1, old.run_id) is None
    with pytest.raises(ValueError, match="invalid_submission_trace"):
        store.create(1, "invalid", body, "demo", submission_trace=("0" * 32, "f" * 16))
    assert len(store.list_tasks(1)) == 1
    parent = ("1" * 32, "2" * 16)
    state, _, _ = store.create(1, "new", body, "demo", submission_trace=parent)
    store.create(1, "new", body, "demo", submission_trace=("3" * 32, "4" * 16))
    assert ResearchStore(tmp_path).submission_trace(1, state.run_id) == parent
    with pytest.raises(NotFound):
        store.submission_trace(2, state.run_id)


def test_authenticated_api_to_worker_trace(tmp_path, monkeypatch):
    from opentelemetry import trace
    sdk = pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider, exporter = sdk.TracerProvider(), InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)
    for name in ("SCHOLARLENS_OTEL_ENABLED", "SCHOLARLENS_RESEARCH_ENABLED", "SCHOLARLENS_E11_ENABLED"):
        monkeypatch.setenv(name, "true")
    app = create_demo(tmp_path / "runtime", "", "profile-fixture")
    password = uuid4().hex
    account = {"username": "trace-" + uuid4().hex, "password": password}
    with TestClient(app) as client:
        assert client.post("/api/auth/register", json=account).status_code == 201
        auth = client.post("/api/auth/login", json=account).json()["access_token"]
        headers = {"Authorization": "Bearer " + auth, "Idempotency-Key": uuid4().hex,
                   "traceparent": "00-" + "a"*32 + "-" + "b"*16 + "-01"}
        task = {"goal": "综合这两篇论文各自的方法和主要结果。", "scope": {"paper_ids": ["ui:wave", "ui:lens"]}}
        created = client.post("/api/research/tasks", json=task, headers=headers)
        assert created.status_code == 202, created.text
        path = "/api/research/tasks/" + created.json()["task_id"]
        deadline = monotonic() + 20
        while True:
            result = client.get(path, headers=headers)
            assert result.status_code == 200
            if result.json()["state"]["status"] in {"partial", "completed"}:
                break
            assert monotonic() < deadline, result.json()["state"]["status"]
            sleep(0.05)
        assert client.post("/api/research/tasks", json=task, headers=headers).json()["task_id"] == created.json()["task_id"]
    spans = exporter.get_finished_spans()
    api, = [s for s in spans if s.name == "research.api"]
    worker, = [s for s in spans if s.name == "research.task"]
    workflow, = [s for s in spans if s.name == "research.workflow"]
    assert api.parent is None and worker.parent.span_id == api.context.span_id
    assert workflow.parent.span_id == worker.context.span_id
    assert {s.context.trace_id for s in spans} == {api.context.trace_id}
    assert result.json()["trace_ids"] == [format(api.context.trace_id, "032x")] != ["a"*32]
    assert {"research.plan", "research.retrieve", "research.verify", "research.publication", "research.synthesis"} <= {s.name for s in spans}
    assert all(set(s.attributes) == {"outcome"} and not s.events for s in spans)
    provider.shutdown()
