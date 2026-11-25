"""Named subject and metric binding in descriptive comparisons."""
import pytest

from backend.research.descriptive_plan import comparison_subjects
from tools.research_eval.trace_loss import execute


def test_explicit_titles_are_paper_identifiers():
    assert comparison_subjects('Compare the objectives of “Red” and “Blue”. What evidence supports each?') == []
    assert comparison_subjects("Compare optical sampling with acoustic ranging. Give objectives.") == [
        "optical sampling", "acoustic ranging"]


def test_requested_metric_keeps_other_metrics_out(tmp_path):
    docs = {pid: {"paper_id": pid, "title": pid, "abstract": f"We evaluated accuracy on the {pid} dataset."}
            for pid in ("red", "blue")}
    report = execute("Compare recall metrics.", list(docs), docs, "e11:test", tmp_path, "E11")["report"]
    assert not report["answer_groups"]["direct"]
    assert all(f["requested_metric"] == "recall" for req in report["field_requirements"] for f in req["fields"])


@pytest.mark.parametrize(("qualifier", "expected"), [
    ("This new representation takes into account platform occupancy and switch capacity.", True),
    ("An unrelated representation takes into account platform occupancy and switch capacity.", False),
    ("This representation might take into account platform occupancy and switch capacity.", False),
    ("", False),
])
def test_constraints_representation_requires_adjacent_explicit_scope(tmp_path, qualifier, expected):
    first = "This paper introduces a binary representation for railway rescheduling."
    abstract = " ".join(filter(None, (first, qualifier)))
    docs = {
        "rail": {"paper_id": "rail", "title": "Railway Rescheduling", "abstract": abstract},
        "shop": {"paper_id": "shop", "title": "Job-shop policy gradients",
                 "abstract": "We model job-shop policy gradients as a Markov decision process."},
    }
    goal = ("Compare railway rescheduling constraints with job-shop policy gradients. "
            "Give the data representation and objective for each.")
    report = execute(goal, list(docs), docs, "fixture:constraints", tmp_path, "E11", pra_arm="G")["report"]
    requirements = [f for req in report["field_requirements"] for f in req["fields"]]
    rail = next(f for f in requirements if f["subject"] == "railway rescheduling constraints"
                and f["facet"] == "representation")
    decision = report["answerability"]["fields"][rail["field_id"]]
    assert (decision["status"] == "answerable") is expected
    if expected:
        binding, = decision["bindings"]
        claim = next(c for c in report["claims"] if c["claim_id"] == binding["claim_id"])
        source = next(s for s in report["sources"] if s["evidence_id"] == binding["evidence_id"])
        assert claim["statement"] == source["quote"] == abstract
        assert claim["paper_ids"] == ["rail"]
