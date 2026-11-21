"""A read that missed its deadline cannot hold the worker or publish a late quote."""

from datetime import datetime, timedelta, timezone
from threading import Event
import time

from backend.research.harness import bounded_read
from backend.research.reports import generate_report
from backend.tests.research.test_claim_report import setup


def test_final_read_releases_worker_before_slow_source_returns(tmp_path, monkeypatch):
    state, store, registry = setup(tmp_path)
    entered, finished = Event(), Event()
    previous = registry.call

    def delayed(name, args):
        entered.set()
        time.sleep(0.2)
        try:
            return previous(name, args)
        finally:
            finished.set()

    monkeypatch.setattr(registry, "call", delayed)
    state.budget.deadline = datetime.now(timezone.utc) + timedelta(milliseconds=50)
    start = time.monotonic()
    report = generate_report(state, store, registry)
    elapsed = time.monotonic() - start
    assert entered.is_set() and not finished.is_set()
    assert elapsed < 0.19, elapsed
    assert report["status"] == "partial" and report["stop_reason"] == "budget"
    assert not report["sources"] and not report["sections"]["verified"]
    assert state.budget.tool_calls_used == 1
    assert state.actions[-1].error_code == "report_source_budget_exhausted"
    assert state.actions[-1].output_digest is None
    original = store.artifact(1, state.run_id, state.artifact_refs[-2])["content"]
    assert bounded_read(lambda: "next read") == "next read"
    assert finished.wait(timeout=2)
    assert store.artifact(1, state.run_id, state.artifact_refs[-2])["content"] == original
