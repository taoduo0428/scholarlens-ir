"""PRA source selection, independent fields, and withdrawal when a premise disappears."""

from hashlib import sha256
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.research.pra_relations import method_name, verify_derivation
from backend.research.workspace_model import SourceReview
from tools.research_eval.trace_loss import execute


def test_model_nominates_existing_ids_without_choosing_source_coordinates():
    data = {"evidence_id": "e-one", "sentence_id": "s-one", "field": "methods", "origin": "authors"}
    assert SourceReview.model_validate({"selections": [data]}).selections[0].field == "methods"
    with pytest.raises(ValidationError):
        SourceReview.model_validate({"selections": [{**data, "start": 0, "quote": "altered"}]})


@pytest.mark.parametrize("text", [
    "Earlier studies used dynamic programming for scheduling.",
    "We might use dynamic programming for scheduling.",
    "We use dynamic programming only if sufficient time is available.",
    "We use dynamic programming as a baseline for comparison.",
])
def test_qualified_method_cannot_become_an_author_relation(text):
    assert method_name(text) is None


def test_bilingual_pair_uses_exact_spans_and_withdraws_on_premise_loss(tmp_path):
    docs = {
        "p1": {"paper_id": "p1", "title": "Scheduling", "abstract": "We use dynamic programming for scheduling."},
        "p2": {"paper_id": "p2", "title": "资源分配", "abstract": "我们采用动态规划用于计算资源分配。"},
    }
    task = "Compare the methods used in the two papers."
    r = execute(task, list(docs), docs, "test:v8", tmp_path/"pair", "E11", pra_arm="G")["report"]
    edges = [e for e in r["profile_relations"] if e["relation"] == "uses"]
    assert len(edges) == 2
    claims = {c["claim_id"]: SimpleNamespace(**c) for c in r["claims"]}
    sources = {s["evidence_id"]: s for s in r["sources"]}
    assert verify_derivation(edges, claims, sources, docs)
    assert not verify_derivation(edges[:1], claims, sources, docs)
    assert not verify_derivation(edges, claims, {k:v for k,v in sources.items() if v["paper_id"]=="p1"}, docs)
    assert not verify_derivation(edges, claims, sources, {"p1"})
    assert not verify_derivation([{**edges[0], "target": "BERT"}, edges[1]], claims, sources, docs)
    assert len(r["compiled_answer"]) == 12
    for entry in r["compiled_answer"]:
        for item in entry["items"]:
            if item["kind"] == "source":
                assert all(item["text"] in sources[e]["quote"] for e in item["evidence_ids"])
    missing = {**docs, "p2": {**docs["p2"], "abstract": "Earlier studies used dynamic programming for resource allocation."}}
    weaker = execute(task, list(missing), missing, "test:v8:changed", tmp_path/"missing", "E11", pra_arm="G")["report"]
    assert {p for e in weaker["profile_relations"] if e["relation"]=="uses" for p in e["paper_ids"]} == {"p1"}
    assert weaker["answerability"]["status"] == "partially_answerable"


def test_profiles_separate_goals_from_observed_results(tmp_path):
    text = ("We introduce a controller for scheduling jobs. The aim is to reduce waiting time for unobserved jobs. "
            "Previous studies reported a 15% reduction in waiting time.")
    docs = {"p": {"paper_id": "p", "title": "Scheduling jobs", "abstract": text}}
    report = execute("Describe the research objectives.", ["p"], docs, "test:objective",
                     tmp_path/"objective", "E11", pra_arm="B")["report"]
    p = report["research_profiles"][0]
    intended = next(x for x in p["fields"]["research_objective"] if x["quote"].startswith("The aim"))
    assert intended["attribution_sentence_id"] and intended["attribution_sentence_id"] != intended["sentence_id"]
    assert text[intended["start"]:intended["end"]] == intended["quote"]
    assert sha256(intended["quote"].encode()).hexdigest() == intended["quote_hash"]
    assert not p["fields"]["reported_findings"]


@pytest.mark.parametrize(("left", "right", "relation"), [
    ("We use logistic regression for forecasting.", "We use linear regression for forecasting.", "shared_method_family"),
    ("We use BM25 for document retrieval.", "We use BERT for document retrieval.", "different_methods_for_task"),
    ("We use dynamic programming for scheduling.", "我们使用动态规划用于分配资源。", "shared_method"),
    ("We find that yield increases under dry conditions.", "We find that yield decreases under dry conditions.", "different_directions"),
    ("We find that yield increases under dry conditions.", "We find that yield decreases under wet conditions.", None),
    ("We use dynamic programming for scheduling.", "Previous studies used dynamic programming for scheduling.", None),
])
def test_compiled_relations_preserve_scope_and_experimental_conditions(tmp_path, left, right, relation):
    docs = {k: {"paper_id": k, "title": k, "abstract": v} for k, v in (("A", left), ("B", right))}
    r = execute("综合这组论文各自的方法、主要结果和仍待解决的问题。", list(docs), docs,
                "test:v8:overview", tmp_path, "E11", pra_arm="G")["report"]
    derived = [x for x in r["overview"]["findings"] if x["level"] == "derived_synthesis"]
    if relation:
        assert any(x["kind"] == relation and set(x["paper_ids"]) == set(docs) for x in derived)
    else:
        assert not derived
    assert not any(x["kind"] == "causal" for x in derived)
    direct = set(r["sections"]["verified"])
    for claim in r["claims"]:
        if claim["claim_id"] in direct:
            assert len(claim["paper_ids"]) == 1
            assert claim["statement"] in docs[claim["paper_ids"][0]]["abstract"]
