"""Run independent synthetic premises through research, field binding and publication."""
import pytest

from tools.research_eval.trace_loss import execute


def overview(tmp_path, abstracts):
    docs = {str(i): {"paper_id": str(i), "title": f"Study {i}", "abstract": text}
            for i, text in enumerate(abstracts, 1)}
    return execute("综合这组论文各自的方法、主要结果和仍待解决的问题。", list(docs),
                   docs, "fixture:overview-relations", tmp_path, "E11")["report"]


@pytest.mark.parametrize(("sentences", "kind"), [
    (["We prove that the bound holds for compact domains.", "We prove the existence of weak solutions."],
     "shared_research_design"),
    (["We use logistic regression for risk estimation.", "本研究采用逻辑回归用于风险评估。"], "shared_method"),
    (["We use BM25 for document retrieval.", "We use BERT for document retrieval."], "different_methods_for_task"),
    (["We use BM25 for document retrieval.", "We use BM25 for patent search.",
      "We use BM25 for classification."], "shared_method"),
    (["We find that yield increases under dry conditions.",
      "Our results show that yield decreases under dry conditions."], "different_directions"),
    (["We find that yield increases under dry conditions.",
      "Our results show that yield increases under dry conditions."], "shared_direction"),
])
def test_relation_survives_missing_unrelated_fields(tmp_path, sentences, kind):
    report = overview(tmp_path, sentences)
    relations = [r for r in report["overview"]["findings"] if r["level"] == "derived_synthesis"]
    assert [r["kind"] for r in relations] == [kind]
    assert set(relations[0]["paper_ids"]) == {str(i) for i in range(1, len(sentences) + 1)}
    assert report["answerability"]["status"] == "partially_answerable"
    fields = {f["field_id"] for q in report["field_requirements"] for f in q["fields"] if f["facet"] == "overview"}
    bound = {b["claim_id"] for b in report["answerability"]["bindings"] if b["field_id"] in fields}
    assert set(relations[0]["premise_claim_ids"]) <= bound
    assert relations[0]["statement"] in report["markdown"]


@pytest.mark.parametrize("sentences", [
    ["We use BM25 for patent search.", "We use BERT for document retrieval."],
    ["We use BM25 for this task.", "We use BERT for this task."],
    ["We use BM25 for document retrieval.", "Previous studies used BM25 for document retrieval."],
    ["We use BM25 for document retrieval.", "We do not use BM25 for document retrieval."],
    ["We use BM25 for document retrieval.", "We may use BM25 for document retrieval."],
    ["We prove that the bound holds for compact domains.", "If the bound is sharp, we prove that a solution exists."],
    ["We use BM25 for document retrieval.", "We use BM25 for patent search.", "We use BERT for classification."],
    ["We find that yield increases in mice.", "Our results show that yield decreases in humans."],
])
def test_missing_or_unrelated_witnesses_leave_final_relation_open(tmp_path, sentences):
    report = overview(tmp_path, sentences)
    assert not any(r["level"] == "derived_synthesis" for r in report["overview"]["findings"])
    assert report["sections"]["verified"]


def test_parallel_observations_remain_individually_attributed(tmp_path):
    report = overview(tmp_path, ["We developed a telescope. We found a stable signal.",
                                 "We developed a microscope. We observed cellular damage."])
    rows = report["overview"]["findings"]
    assert len(rows) == 2 and all(r["level"] == "paper_observation" for r in rows)
    assert all(len(r["paper_ids"]) == 1 for r in rows)
    assert "逐篇观察" in report["markdown"]
