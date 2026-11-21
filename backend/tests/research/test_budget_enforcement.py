"""Exercise provider and tool limits where untrusted results meet the research graph."""

from datetime import datetime, timedelta, timezone
from threading import Event

import pytest

from backend.research.graph import ResearchGraph
from backend.research.schemas import Budget, Finish, Scope, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolError, ToolRegistry


def test_large_tool_result_fails_closed(monkeypatch):
    registry = ToolRegistry(
        LocalCorpus([], "test-corpus"), owner_id=1, scope=Scope(), generation="test-corpus"
    )
    monkeypatch.setattr(registry, "_search_papers", lambda req: {"papers": ["x" * 128001]})
    with pytest.raises(ToolError, match="tool_output_limit"):
        registry.call("search_papers", {"query": "metric"})


@pytest.mark.parametrize("calls", [0, 1])
def test_provider_cannot_exceed_call_or_wall_clock_budget(tmp_path, calls):
    corpus = LocalCorpus([], "test-corpus")
    store = ResearchStore(tmp_path)
    task = TaskInput(goal="Which method produced the result?", mode="personal_model")
    state, rev, _ = store.create(1, "id", task, corpus.generation)
    state.status = "running"
    state.budget = Budget(
        max_model_calls=calls, deadline=datetime.now(timezone.utc) + timedelta(seconds=0.4)
    )
    store.save(1, state, rev, "started", "bounds")
    entered, release, returned = Event(), Event(), Event()

    def slow_decision(view, remaining):
        entered.set()
        release.wait(timeout=2)
        returned.set()
        return Finish(reason="blocked")

    graph = ResearchGraph(
        store,
        lambda s: ToolRegistry(
            corpus, owner_id=1, scope=s.task.scope, generation=corpus.generation
        ),
        choose=slow_decision,
    )
    try:
        final = graph.run(1, state.run_id)
        assert final.status == "partial" and final.stop_reason == "budget"
        assert not returned.is_set() and not final.decisions and not final.evidence_refs
        assert final.budget.model_calls_used == calls and entered.is_set() == bool(calls)
    finally:
        release.set()
        graph.close()
