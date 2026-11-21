"""Publication and question isolation checks run through the existing research graph."""

from types import SimpleNamespace as Box

import pytest

from backend.research.field_contract import SourceCoverage
from backend.research.field_gate import ancestors, classify_gap
from tools.research_eval.trace_loss import execute


def run(tmp_path, goal, abstract):
    paper = {"paper_id": "orange", "title": "Orange chamber", "abstract": abstract}
    trace = execute(goal, ["orange"], {"orange": paper}, "fixture:e9-dev", tmp_path, "E9")
    return trace["report"]


@pytest.mark.parametrize(
    ("goal", "text", "expected"),
    [
        (
            'Quote the first sentence of the abstract of "Orange chamber".',
            "The chamber uses a reflective coating.",
            "answerable",
        ),
        (
            "What is the material of the clamp?",
            "The material of the chamber is silver.",
            "insufficient_evidence",
        ),
        (
            "What are the PDF coordinates of the chamber?",
            "The chamber has four windows.",
            "source_capability_mismatch",
        ),
        (
            "What is the material of the chamber?",
            "The material of the chamber is silver.",
            "answerable",
        ),
        (
            "What is the material of the chamber?",
            "The material of the chamber is silver. The material of the chamber is copper.",
            "conflicted",
        ),
        (
            'Quote the first sentence of the abstract of "Orange chamber" and provide its PDF page number.',
            "The chamber uses a reflective coating.",
            "partially_answerable",
        ),
        (
            "What are the material and height of the chamber?",
            "The material of the chamber is copper.",
            "partially_answerable",
        ),
    ],
)
def test_field_release(tmp_path, goal, text, expected):
    report = run(tmp_path, goal, text)
    gate = report["answerability"]
    assert gate["status"] == expected, gate
    assert bool(report["sections"]["verified"]) == (
        expected in {"answerable", "partially_answerable"}
    )
    if expected == "partially_answerable":
        assert len(report["field_requirements"][0]["fields"]) == 2
        assert {v["status"] for v in gate["fields"].values()} & {
            "insufficient_evidence",
            "source_capability_mismatch",
        }
    for b in gate["bindings"]:
        assert b["claim_id"] in report["sections"]["verified"]
        assert b["source_version"] == "fixture:e9-dev" and b["locator"]["field"] == "abstract"


def test_no_proof_of_absence_without_complete_coverage():
    incomplete = SourceCoverage(scope=["a"], represented=[], searches=1)
    assert classify_gap(incomplete, {}, {}, "insufficient_evidence")[1] == "information_not_found"
    assert (
        classify_gap(
            incomplete.model_copy(update={"permission_denied": True}),
            {},
            {},
            "insufficient_evidence",
        )[0]
        == "blocked_by_permission"
    )
    assert (
        classify_gap(
            incomplete.model_copy(update={"exhaustive": True}), {}, {}, "insufficient_evidence"
        )[0]
        == "unavailable_in_scope"
    )


def test_question_can_only_consume_its_explicit_dependencies():
    lineage = ancestors(
        [
            Box(question_id="a", dependencies=[]),
            Box(question_id="b", dependencies=[]),
            Box(question_id="c", dependencies=["a"]),
        ]
    )
    assert lineage["c"] == {"a", "c"}
    assert lineage["a"] == {"a"}


def test_comparison_requires_matching_conditions(tmp_path):
    docs = {
        p: {
            "paper_id": p,
            "title": "Chamber results",
            "abstract": f"Chamber accuracy was {score}% on dataset: {dataset}, setup: bench, protocol: blind.",
        }
        for p, score, dataset in [("red", 73, "east"), ("blue", 87, "west")]
    }
    report = execute(
        "Compare chamber accuracy across the two experiments.",
        list(docs),
        docs,
        "fixture:e9-dev",
        tmp_path,
        "E9",
    )["report"]
    assert not report["sections"]["verified"]
    assert "not_comparable" in report["answerability"]["questions"].values()
