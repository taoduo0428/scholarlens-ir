from hashlib import sha256
import pytest

from backend.research.claim_verifier import new_claim
from backend.research.premises import compare_premises
from backend.research.synthesis import judge
from tools.research_eval.trace_loss import execute


def source(paper, quote):
    return {"evidence_id": "e-" + paper, "paper_id": paper, "quote": quote,
            "quote_hash": sha256(quote.encode()).hexdigest()}


@pytest.mark.parametrize(("second_conditions", "expected"), [
    ("dataset: Amber, setup: fixed, protocol: sealed", "aligned_reported_conditions"),
    ("dataset: Silver, setup: fixed, protocol: sealed", "different_conditions"),
    ("dataset: Amber", "missing_conditions"),
    ("", "missing_conditions"),
])
def test_explicit_premises_required_for_semantic_conflict(second_conditions, expected):
    a = source("prismA", "The prism is stable, dataset: Amber, setup: fixed, protocol: sealed.")
    b = source("prismB", "The prism is not stable" + (", " + second_conditions if second_conditions else "") + ".")
    claims = [new_claim("q1", r["quote"], "fact", [r]).model_copy(update={"support_status": "verified"})
              for r in (a, b)]
    conflicts, apparent = compare_premises(claims, {r["evidence_id"]: r for r in (a, b)})
    observed = conflicts if expected.startswith("aligned") else apparent
    assert len(conflicts) + len(apparent) == 1
    assert observed[0]["basis"] == expected


def test_count_binds_the_requested_object_to_the_number():
    goal = "How many mirrors were used in the alignment bench?"
    for quote, supported in (
        ("The alignment bench used 12 lamps and tested mirrors.", False),
        ("The alignment bench used 12 mirrors and tested lamps.", True),
    ):
        r = source("optic", quote)
        claim = new_claim("q1", quote, "fact", [r])
        verdict = judge(claim, [claim], {r["evidence_id"]: r}, goal)
        assert verdict["provenance_valid"]
        assert (verdict["semantic_support"] == "supported") == supported


def test_count_gap_propagates_through_actual_report(tmp_path):
    docs = {"p": {"paper_id": "p", "title": "Alignment bench",
                  "abstract": "The alignment bench used 12 lamps and tested mirrors."}}
    trace = execute("How many mirrors were used in the alignment bench?", ["p"], docs, "fixture:count",
                    tmp_path, "V5")
    assert trace["status"] == "partial" and not trace["report"]["sections"]["verified"]
    assert trace["assessments"]["q1"]["missing_requirements"]
    assert trace["report"]["sources"]
    assert all(edge["relation"] != "supports" for edge in trace["report"]["graph"]["claim_evidence"])


def test_dependency_reorder_persisted_after_actual_search(tmp_path):
    docs = {"p": {"paper_id": "p", "title": "Optical calibration",
                  "abstract": "Optical calibration adjusts the focal length of a mirror in the laboratory."}}
    trace = execute("Compare optical calibration protocols across studies.", ["p"], docs,
                    "fixture:rotation", tmp_path, "V4")
    plan = trace["question_plan"]
    assert plan["plan_version"] >= 2 and "prioritize" in plan["revisions"][0]
    assert next(n for n in plan["graph"]["nodes"] if n["id"] == "q3")["dependencies"] == ["q1", "q2"]


@pytest.mark.parametrize("later_cancel", [True, False])
def test_checkpoint_consumes_only_matching_control(tmp_path, later_cancel):
    from backend.research.schemas import TaskInput
    from backend.research.store import ResearchStore
    from backend.research.worker import Worker

    store = ResearchStore(tmp_path)
    state, rev, _ = store.create(1, "pause", TaskInput(goal="Summarize mirror alignment"), "fixture")
    worker = Worker(store, lambda _: None, check_owner=lambda _: True)
    worker.control(1, state.run_id, "paused")
    if later_cancel:
        worker.control(1, state.run_id, "cancelled")
    state.status = "paused"
    store.save(1, state, rev, "paused", "ack-pause")
    assert store.get(1, state.run_id)[0].status == "paused"
    assert worker._command(1, state.run_id) == ("cancelled" if later_cancel else None)
