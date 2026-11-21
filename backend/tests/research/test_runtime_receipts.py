"""Provider accounting, private spans, and worker recovery on isolated stores."""

import json
import time

import httpx
import pytest

from backend.config import Settings
from backend.research.accounting import spending
from backend.research.harness import bounded_read
from backend.research.schemas import TaskInput
from backend.research.store import Conflict, NotFound, ResearchStore
from backend.research.telemetry import metering, span
from backend.research.worker import Worker
from backend.research.workspace_model import propose


@pytest.mark.parametrize(
    "usage,expected",
    [
        (
            {
                "prompt_tokens": 20,
                "completion_tokens": 3,
                "prompt_tokens_details": {"cached_tokens": 6},
            },
            (20, 3, 6),
        ),
        ({"input_tokens": 4, "output_tokens": 1}, (4, 1, None)),
        ({"prompt_tokens": -1, "completion_tokens": True}, (None, None, None)),
        (None, (None, None, None)),
    ],
)
def test_local_provider_receipt_and_checkpoint_ownership(tmp_path, usage, expected):
    store = ResearchStore(tmp_path)
    state, _, _ = store.create(1, "key", TaskInput(goal="Review conditions"), "test")
    cfg = Settings(
        ai_personal=True,
        ai_model="fixture",
        ai_api_key="test-only-credential",
        ai_protocol="chat_completions",
        ai_base_url="https://provider.invalid/v1",
    )
    result = {"choices": [{"message": {"content": '{"labels":[]}'}}], "usage": usage}

    def transport(req):
        return httpx.Response(200, json=result)

    with metering(lambda row: store.record_usage(1, state.run_id, row)):
        response = bounded_read(propose, cfg, "analysis", {}, 3, httpx.MockTransport(transport))
    assert response.labels == []
    state.budget.model_calls_used = 1
    receipts = store.usage(1, state.run_id)
    assert receipts[0]["provider"] == "custom"
    assert cfg.ai_api_key not in json.dumps(receipts) and "invalid" not in json.dumps(receipts)
    totals = spending(state, receipts)
    assert (totals["input_tokens"], totals["output_tokens"], totals["cached_tokens"]) == expected
    assert totals["tokens"] == (None if expected[0] is None else sum(expected[:2]))
    state.budget.model_calls_used = 2
    assert spending(state, receipts)["tokens"] is None
    with pytest.raises(NotFound):
        store.usage(2, state.run_id)
    restored = store.restore(
        store.backup(tmp_path / "snapshot.sqlite3") or tmp_path / "snapshot.sqlite3",
        tmp_path / "restore",
    )
    assert restored.usage(1, state.run_id) == receipts


def test_corrupt_queue_entry_keeps_worker_and_other_owner_alive(tmp_path):
    store = ResearchStore(tmp_path)
    first, _, _ = store.create(1, "bad", TaskInput(goal="Review failed state"), "test")
    second, _, _ = store.create(
        2, "ok", TaskInput(goal="Review valid state", mode="personal_model"), "test"
    )
    with store._db(write=True) as db:
        db.execute("UPDATE tasks SET state_json=? WHERE id=?", ("invalid-state", str(first.run_id)))
    worker = Worker(store, None, check_owner=lambda _: True)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while (
            time.monotonic() < deadline
            and store.get(2, second.run_id)[0].status != "awaiting_credentials"
        ):
            time.sleep(0.02)
        assert (
            worker.thread.is_alive()
            and store.get(2, second.run_id)[0].status == "awaiting_credentials"
        )
        assert store.list_tasks(1)[0]["quarantined"] == 1 and not store.recovery_tasks()
        with pytest.raises(Conflict, match="research_state_integrity"):
            store.get(1, first.run_id)
        with pytest.raises(NotFound):
            store.get(2, first.run_id)
        with store._db() as db:
            assert (
                db.execute(
                    "SELECT state_json FROM tasks WHERE id=?", (str(first.run_id),)
                ).fetchone()[0]
                == "invalid-state"
            )
    finally:
        worker.close()


def test_optional_sdk_private_spans(monkeypatch):
    sdk = pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = sdk.TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)
    monkeypatch.setenv("SCHOLARLENS_OTEL_ENABLED", "true")

    def error():
        with span("verify"):
            raise ValueError("private task and user evidence")

    with span("task"):
        with pytest.raises(ValueError):
            bounded_read(error)
    child, parent = exporter.get_finished_spans()
    assert (
        parent.context.span_id == child.parent.span_id
        and parent.context.trace_id == child.context.trace_id
    )
    assert (
        dict(child.attributes) == {"outcome": "error", "error.category": "validation"}
        and not child.events
    )
    assert "private task" not in child.to_json() and child.end_time >= child.start_time
    monkeypatch.delenv("SCHOLARLENS_OTEL_ENABLED")
    with span("task"):
        pass
    assert len(exporter.get_finished_spans()) == 2
    provider.shutdown()
