from copy import deepcopy

import pytest

from tools.research_eval.e10_pack import retrieval_rankings
from tools.research_eval.e10_score import score
from tools.research_eval.review_pack import canonical_sha


def packet():
    docs = {"p": "real text"}
    pack = {
        "papers": {"p": {"abstract_sha256": canonical_sha(docs["p"])}},
        "tasks": [{"task_id": "q", "allowed_papers": ["p"]}],
    }
    pack["dataset_hash"] = canonical_sha(pack)
    run = {
        "dataset_hash": pack["dataset_hash"],
        "tasks": {
            "q": {
                "claims": {"c": {}},
                "fields": {"f": ["field", "answerable"]},
                "passages": {"e": ["p", "abstract:chars:0-4"]},
                "ranking": ["p"],
                "answerability": "answerable",
                "terminal": "completed",
                "tools": 1,
                "tool_success": 1,
                "tool_records": 1,
                "latency_ms": 3,
                "recovery_successes": None,
                "recovery_attempts": None,
                "tokens": None,
                "cost": None,
            }
        },
    }
    judgment = {
        "relevant_papers": {"p": 3},
        "relevant_passages": [["p", "abstract:chars:0-4"]],
        "required_fields": {"field": "f"},
        "gold_answer": "real",
        "expected_claims": {"real": "c"},
        "claim_support": {"c": "supported"},
        "evidence_alignment": {"e": True},
        "answerability": "answerable",
        "contradiction": False,
        "comparability": "not_applicable",
        "refusal_correctness": None,
        "decomposition_correct": True,
        "tool_selection_correct": True,
        "overall_task_success": True,
        "rationale": "test judgment",
    }
    sheet = {
        "role": "reviewer",
        "version": "e10/1",
        "dataset_hash": pack["dataset_hash"],
        "run_hash": canonical_sha(run),
        "human_confirmed": True,
        "reviewer_id": "a",
        "reviewed_at": "2026-11-21T09:00:00+08:00",
        "tasks": {"q": judgment},
    }
    return pack, run, docs, sheet


def test_pending_and_disputed_reviews_stay_out_of_scores():
    pack, run, docs, a = packet()
    assert score(pack, run, docs)["metrics"]["task_success_rate"] is None
    b = deepcopy(a)
    b["reviewer_id"] = "b"
    assert score(pack, run, docs, [a, b])["confirmed"] == 1
    b["tasks"]["q"]["overall_task_success"] = False
    disputed = score(pack, run, docs, [a, b])
    assert disputed["confirmed"] == 0 and disputed["rows"][0]["state"] == "disputed"
    resolution = dict(a, role="adjudicator", reviewer_id="c")
    assert score(pack, run, docs, [a, b], resolution)["adjudicated"] == 1
    with pytest.raises(ValueError):
        score(pack, run, docs, [a, b], dict(resolution, reviewer_id="b"))


@pytest.mark.parametrize(
    "change",
    [
        {"human_confirmed": False},
        {"dataset_hash": "other"},
        {"reviewer_id": "A"},
        {"run_hash": "other"},
        {"reviewed_at": None},
    ],
)
def test_invalid_review_receipts(change):
    pack, run, docs, a = packet()
    with pytest.raises(ValueError):
        score(pack, run, docs, [a, dict(a, **({"reviewer_id": "b"} | change))])


def test_entailment_is_agreement_on_explicit_judgments():
    pack, run, docs, a = packet()
    run["tasks"]["q"]["entailment_candidates"] = {"c": {"prediction": "verified"}}
    a["run_hash"] = canonical_sha(run)
    a["tasks"]["q"]["entailment_gold"] = {"c": "contradicted"}
    final = score(pack, run, docs, [a, dict(a, reviewer_id="b")])
    assert final["metrics"]["claim_support_precision"] == 1
    assert final["metrics"]["entailment_accuracy"] == 0


def test_source_coordinates_and_candidate_order():
    pack, run, docs, a = packet()
    a["tasks"]["q"]["relevant_passages"] = [["p", "abstract:chars:0-200"]]
    with pytest.raises(ValueError, match="locator"):
        score(pack, run, docs, [a, dict(a, reviewer_id="b")])
    assert retrieval_rankings(
        [
            {"phase": "research", "passages": [{"paper_id": "b"}]},
            {"phase": "research", "papers": [{"paper_id": "a"}, {"paper_id": "b"}]},
            {"phase": "publication", "papers": [{"paper_id": "c"}]},
        ]
    ) == {"ranking": ["b", "a"], "passage_ranking": ["b"], "discovery_ranking": ["a", "b"]}
