"""Operational regressions for E10, isolated from installation data."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from backend.research.schemas import TaskInput
from backend.research.store import NotFound, ResearchStore
from tools.research_eval.v6_model import run


def test_model_exercises_all_stages_without_external_network():
    result = run(controlled=True)
    assert result["status"] == "PASS", result
    assert result["calls"] == result["spending"]["provider_receipts"] == 4


def test_model_without_key_never_calls_provider(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    assert run()["status"] == "BLOCKED"


def test_writer_waits_then_recovers_without_cross_owner_effects(tmp_path):
    store = ResearchStore(tmp_path)
    task = TaskInput(goal="What evidence was measured?")
    first = store.create(1, "same", task, "g1")[0]
    ready = Event()

    def write_other():
        ready.set()
        return store.create(2, "same", task, "g1")

    with ThreadPoolExecutor(max_workers=1) as pool:
        with store._db(write=True):
            future = pool.submit(write_other)
            assert ready.wait(2)
            assert store.get(1, first.run_id)[0].status == "queued"
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
        other, revision, created = future.result(timeout=4)
    assert created and revision == 0 and first.run_id != other.run_id
    reopened = ResearchStore(tmp_path)
    assert len(reopened.events(2, other.run_id)) == 1
    with pytest.raises(NotFound):
        reopened.events(1, other.run_id)
    with pytest.raises(NotFound):
        reopened.trace_ids(2, first.run_id)
    reopened.record_trace(1, first.run_id, "1" * 32)
    reopened.record_trace(1, first.run_id, "1" * 32)
    assert reopened.trace_ids(1, first.run_id) == ["1" * 32]
