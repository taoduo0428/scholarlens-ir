"""Exercise E11 at the application graph, including negative and partial cases."""
from hashlib import sha256

import pytest

from backend.research.research_intent import research_intent
from backend.research.research_profile import attribution
from tools.research_eval.trace_loss import execute


@pytest.mark.parametrize(("goal", "expected"), [
    ("Describe the research.", "description"), ("给出研究综述", "literature_synthesis"),
    ("比较研究方法", "method_comparison"), ("比较实验条件", "condition_comparison"),
    ("比较评价指标", "metric_comparison"), ("比较方法，哪一个性能更好？", "performance_ranking"),
    ("Which conditions cause the change?", "causal_analysis"),
    ("这些发现矛盾吗", "contradiction_analysis"), ("Identify open questions", "gap_discovery"),
    ("分析历年研究趋势", "trend_analysis"),
])
def test_intents(goal, expected):
    assert research_intent(goal) == expected


def test_qualified_statements():
    assert attribution("A mirror was developed in this study.")[1] >= {"methods"}
    assert attribution("It achieved a smaller error.", "We developed a mirror.")[1] >= {"reported_findings"}
    assert "reported_findings" not in attribution("Previous studies achieved a smaller error.")[1]
    assert "reported_findings" not in attribution("This may improve measurement.")[1]


@pytest.mark.parametrize("missing", [True, False])
def test_methods_do_not_require_metric_alignment(tmp_path, missing):
    docs = {pid: {"paper_id": pid, "title": pid, "abstract": text} for pid, text in [
        ("paper-a", "A red mirror was developed in this study."),
        ("paper-b", "Previous studies used a lens." if missing else "We developed a blue optical lens."),
    ]}
    trace = execute("Compare the methods used in the two papers.", list(docs), docs, "fixture:e11", tmp_path, "E11")
    r = trace["report"]
    assert r["research_intent"] == "method_comparison"
    assert r["answerability"]["status"] == ("partially_answerable" if missing else "answerable")
    assert len(r["answer_groups"]["direct"]) == (1 if missing else 2)
    for profile in r["research_profiles"]:
        for hit in profile["fields"]["methods"]:
            src = docs[hit["paper_id"]]["abstract"]
            assert hit["quote"] == src[hit["start"]:hit["end"]]
            assert sha256(hit["quote"].encode()).hexdigest() == hit["quote_hash"]
    if missing:
        assert any("first_observed_loss" in d for d in r["answerability"]["fields"].values())


def test_ranking_stays_unresolved(tmp_path):
    docs = {p: {"paper_id": p, "title": p, "abstract": f"We developed a telescope for {p}."}
            for p in ["red", "blue"]}
    trace = execute("Rank the performance of the two methods.", list(docs), docs, "fixture:e11", tmp_path, "E11")
    assert trace["report"]["research_intent"] == "performance_ranking"
    assert not trace["report"]["answer_groups"]["direct"]
