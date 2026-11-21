"""Multi-paper coverage and typed decisions through the normal persisted graph."""

import json

import pytest

from backend.research.graph import ResearchGraph
from backend.research.reports import generate_report
from backend.research.schemas import Extract, Read, Replan, Scope, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolRegistry
from backend.research.tools.passages import passages_for


class TopHitCorpus(LocalCorpus):
    def discover(self, req, owner_id, scope):
        if not req.paper_ids:
            return self.global_hits
        return super().discover(req, owner_id, scope)


def run_scoped(root, *, second=None, typed=None, missing=False, no_discovery=False):
    docs = [
        {
            "paper_id": "first",
            "title": "Atlas",
            "abstract": "Atlas uses a lexical retrieval method.",
        }
    ]
    if not missing:
        docs.append(
            {
                "paper_id": "second",
                "title": "Second experiment",
                "abstract": second or "Atlas uses a graph method.",
            }
        )
    corpus = TopHitCorpus(docs, "frozen")
    corpus.global_hits = [] if no_discovery else ["first"]
    store = ResearchStore(root)
    mode = "personal_model" if typed else "evidence_only"
    state, _, _ = store.create(
        11,
        "case",
        TaskInput(
            goal="Describe the Atlas method", scope=Scope(paper_ids=["first", "second"]), mode=mode
        ),
        corpus.generation,
    )
    calls = []

    class LoggedRegistry(ToolRegistry):
        def call(self, tool, payload):
            calls.append((tool, payload))
            return super().call(tool, payload)

    def choose(view, timeout):
        if len(view["queries"]) == 0:
            from backend.research.schemas import Search

            return Search(subtask_id="s1", query="Atlas method")
        if typed == "read":
            row = next(r for r in passages_for(docs[1]) if r["field"] == "abstract")
            return Read(
                paper_id="second", chunk_ids=[row["chunk_id"]], purpose="Read the Atlas method"
            )
        if typed == "extract":
            return Extract(subtask_id="s1", paper_ids=["second"], slots=["method"])
        return Replan(missing_slots=["method"], reason="Inspect the missing method paper")

    graph = ResearchGraph(
        store,
        lambda s: LoggedRegistry(
            corpus, owner_id=11, scope=s.task.scope, generation=corpus.generation
        ),
        choose=choose if typed else None,
        report=generate_report,
    )
    try:
        final = graph.run(11, state.run_id)
    finally:
        graph.close()
    report = json.loads(store.artifact(11, final.run_id, final.artifact_refs[-2])["content"])
    return final, calls, report


def test_scope_recovers_a_paper_outside_top_discovery(tmp_path):
    final, calls, report = run_scoped(tmp_path)
    assert final.status == "completed"
    assert {r.paper_id for r in final.evidence_refs} == {"first", "second"}
    assert any(
        tool == "search_passages" and args.get("paper_ids") == ["second"] for tool, args in calls
    )
    assert final.budget.rounds_used == 2 and not report["unresolved"]


@pytest.mark.parametrize("missing", [True, False])
def test_scope_retains_source_and_retries_missing_evidence_twice(tmp_path, missing):
    final, calls, report = run_scoped(
        tmp_path, second="Unrelated information about rocks.", missing=missing
    )
    assert (final.status, final.stop_reason, final.budget.rounds_used) == ("partial", "plateau", 3)
    assert [q.result_summary.endswith(", 0 new verified passages") for q in final.queries] == [
        False,
        True,
        True,
    ]
    assert {r.paper_id for r in final.evidence_refs} == {"first"}
    assert (
        sum(
            tool == "search_passages" and args.get("paper_ids") == ["second"]
            for tool, args in calls
        )
        == 2
    )
    assert any("second" in reason for reason in report["unresolved"])


@pytest.mark.parametrize(
    "typed,tool",
    [
        ("read", "read_paper_chunks"),
        ("extract", "extract_method_results"),
        ("replan", "search_passages"),
    ],
)
def test_typed_decision_closes_a_missing_paper(tmp_path, typed, tool):
    final, calls, report = run_scoped(tmp_path, typed=typed)
    assert [event.action.kind for event in final.decisions] == ["search", typed]
    assert any(
        name == tool and (args.get("paper_id") == "second" or args.get("paper_ids") == ["second"])
        for name, args in calls
    )
    assert final.status == "completed" and final.budget.model_calls_used == 2
    assert {row["paper_id"] for row in report["sources"]} == {"first", "second"}


def test_no_discovery_hits_do_not_let_an_unavailable_paper_hide_a_visible_source(tmp_path):
    final, calls, report = run_scoped(tmp_path, missing=True, no_discovery=True)
    assert (final.status, final.stop_reason, final.budget.rounds_used) == ("partial", "plateau", 3)
    assert {source["paper_id"] for source in report["sources"]} == {"first"}
