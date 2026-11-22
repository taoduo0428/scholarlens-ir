"""Exercise attributed model-design relations at the report publication boundary."""
import pytest

from backend.tests.research.test_e11_overview_relations import overview


PROPOSAL = "We propose a mathematical model of coastal sediment transport."
MECHANISM = "In our model, we introduce a feedback between water depth and vegetation density."
OTHER = "我们构建了用于刻画积雪厚度变化的数学模型。"


@pytest.mark.parametrize("abstracts", [
    (PROPOSAL, MECHANISM),
    (MECHANISM, PROPOSAL, OTHER),
    ("We propose a flow network model for river discharge prediction.",
     "We develop a lattice-based model that reproduces freckle distributions."),
])
def test_published_comparison_contains_each_owned_action(tmp_path, abstracts):
    report = overview(tmp_path, abstracts)
    findings = [r for r in report["overview"]["findings"] if r["level"] == "derived_synthesis"]
    assert len(findings) == 1
    relation = findings[0]
    assert relation["kind"] == "shared_research_design"
    claims = {c["claim_id"]: c for c in report["claims"]}
    sources = {s["evidence_id"]: s for s in report["sources"]}
    assert len(relation["premise_claim_ids"]) == len(abstracts)
    for cid in relation["premise_claim_ids"]:
        claim = claims[cid]
        pid, = claim["paper_ids"]
        source = sources[claim["evidence_ids"][0]]
        assert source["paper_id"] == pid
        assert claim["statement"] == abstracts[int(pid) - 1]
        assert claim["statement"] in source["quote"]
        assert f"《Study {pid}》 — {claim['statement']}" in relation["statement"]
    assert " ".join(relation["statement"].splitlines()) in report["markdown"].replace(r"\-", "-")


@pytest.mark.parametrize("other", [
    "",
    "A mathematical model of coastal sediment transport exists.",
    "Previous studies propose a mathematical model of coastal sediment transport.",
    "We plan to develop a mathematical model of sediment transport.",
    "We did not develop a mathematical model of sediment transport.",
    "We propose a model selection method for coastal sediment transport.",
    "We propose a method to evaluate a model of coastal sediment transport.",
    "We propose a tool using model for coastal erosion.",
    "We propose a review of their model for coastal sediment transport.",
    "We propose a model of sediment transport if measurements become available.",
    "We propose a model for the.",
    "In our model, we discuss a feedback between transport and storage.",
])
def test_unattributed_or_incomplete_model_details_do_not_license_relation(tmp_path, other):
    report = overview(tmp_path, (PROPOSAL, MECHANISM, other))
    assert not any(r["level"] == "derived_synthesis" for r in report["overview"]["findings"])
