"""Check attribution, report provenance and refusal without any live provider."""
import pytest

from backend.research.paper_findings import roles
from tools.research_eval.trace_loss import execute


@pytest.mark.parametrize("text", [
    "Previous studies used a novel method and improved performance.",
    "We hope to demonstrate a gain in future work.",
    "The authors' affiliation is an institute of robotics.",
])
def test_background_cannot_supply_a_method_or_result(text):
    assert not roles(text)


def test_method_and_finding_are_attributed_and_gaps_visible(tmp_path):
    papers = {p: {"paper_id": p, "title": p, "abstract": (
        f"We developed a {p} telescope. We found a stable signal with the {p} mirror.")}
        for p in ("red", "blue")}
    trace = execute("Give an overview of the methods, results and open questions.", list(papers),
                    papers, "fixture:e10", tmp_path, "E10")
    report = trace["report"]
    findings = [r for r in report["overview"]["findings"] if r["level"] == "derived_synthesis"]
    assert findings and report["answerability"]["status"] == "partially_answerable"
    by_id = {c["claim_id"]: c for c in report["claims"]}
    for f in findings:
        for item in f.get("paper_observations", []):
            for k in ("method_claim_id", "result_claim_id"):
                claim = by_id[item[k]]
                assert claim["paper_ids"] == [item["paper_id"]]
                assert claim["statement"] in papers[item["paper_id"]]["abstract"]
                assert claim["statement"] in f["statement"]
    assert any(f["facet"] == "limitations" for q in report["field_requirements"] for f in q["fields"])
    assert trace["budget"]["tool_calls_used"] <= 10
