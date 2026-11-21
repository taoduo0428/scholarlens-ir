import json

import pytest

from backend.research.questions import make_plan
from backend.research.schemas import TaskInput
from backend.research.store import Conflict, ResearchStore
from tools.research_eval.trace_loss import execute


def docs():
    return {p: {"paper_id": p, "title": p, "abstract":
                f"We use {method} for imaging. Our results show that imaging improves on small samples."}
            for p, method in [("north", "smoothing"), ("south", "calibration")]}


def run(tmp_path, goal, papers=None):
    papers = docs() if papers is None else papers
    return execute(goal, list(papers), papers, "fixture:engineering-dev", tmp_path, "E9.1")


@pytest.mark.parametrize("goal", [
    "Give an overview of the methods and results across the studies.",
    "请综述这两项研究的方法、发现和差异。",
])
def test_derived_overview_through_graph(tmp_path, goal):
    trace = run(tmp_path, goal)
    report = trace["report"]
    assert report["answerability"]["status"] == "answerable"
    rows = report["overview"]["findings"]
    methods = next(f for f in rows if f["kind"] == "method_findings")
    assert set(methods["paper_ids"]) == {"north", "south"}
    direct = {c["claim_id"]: c for c in report["claims"] if c["claim_id"] in report["sections"]["verified"]}
    assert set(methods["premise_claim_ids"]) <= direct.keys()
    assert methods["statement"] not in {c["statement"] for c in direct.values()}
    assert methods["level"] == "derived_synthesis"
    assert "综合研究" in report["markdown"] and report["field_requirements"][0]["original_goal"] == goal
    assert len({f["request"] for q in report["field_requirements"] for f in q["fields"]}) >= 5


def test_missing_and_invalid_cross_paper_support(tmp_path):
    papers = docs()
    papers["south"]["abstract"] = "The authors provide their institution and address."
    report = run(tmp_path, "Give an overview of the methods and findings.", papers)["report"]
    assert not report["sections"]["verified"]
    assert not report["overview"]["findings"]
    assert "south" in report["overview"]["incomplete_papers"]
    for cid in report["sections"]["uncertain"]:
        assert next(c["support_status"] for c in report["claims"] if c["claim_id"] == cid) != "verified"


@pytest.mark.parametrize("goal", ["Give the PDF bounding box coordinates.", "请提供表格单元格的页码。"])
def test_layout_stops_without_text_retries(tmp_path, goal):
    trace = run(tmp_path, goal)
    assert trace["budget"]["tool_calls_used"] == 0
    field = next(iter(trace["report"]["answerability"]["fields"].values()))
    assert (field["status"], field["next_action"]) == ("source_capability_mismatch", "stop")


def test_multilingual_paper_scope_and_independent_counts(tmp_path):
    trace = run(tmp_path, "比较两篇论文的方法、数据集、accuracy 和 recall 指标，并解释结果差异。")
    qs = trace["report"]["field_requirements"]
    assert len(qs) == 3
    all_fields = [f for q in qs for f in q["fields"]]
    assert {(tuple(f["paper_ids"]), f["requested_metric"]) for f in all_fields if f["facet"] == "metric"} == {
        ((p,), m) for p in ("north", "south") for m in ("accuracy", "recall")}
    compares = [f for f in all_fields if f["facet"] == "comparison"]
    assert all(f["min_papers"] == 2 and f["min_evidence"] == 1 for f in compares)
    assert not trace["report"]["sections"]["verified"]


def planned(tmp_path):
    store = ResearchStore(tmp_path)
    task, rev, _ = store.create(7, "key", TaskInput(goal="Compare accuracy across two papers."), "fixture")
    task.question_plan = make_plan(task)
    task.status = "running"
    rev = store.save(7, task, rev, "started", "first")
    return store, task, rev


@pytest.mark.parametrize("change", ["question", "edge"])
def test_plan_sealed_on_save_and_restart(tmp_path, change):
    store, task, rev = planned(tmp_path)
    restarted = ResearchStore(tmp_path)
    assert restarted.checkpoint(7, task.run_id, rev).question_plan == task.question_plan
    record = restarted.plan_metadata(7, task.run_id)
    assert len(record["plan_sha256"]) == 64 and record["plan_version"] == 1 and record["created_at"]
    recovered, _ = restarted.get(7, task.run_id)
    if change == "question":
        recovered.question_plan.graph.nodes[0].question = "Which different facts apply?"
    else:
        recovered.question_plan.graph.nodes[-1].dependencies = ["q2"]
    with pytest.raises(Conflict, match="immutable question plan"):
        restarted.save(7, recovered, rev, "step", "changed")
    with store._db(write=True) as db:
        db.execute("UPDATE tasks SET state_json=? WHERE id=?", (recovered.model_dump_json(), str(task.run_id)))
    with pytest.raises(Conflict, match="question_plan_integrity"):
        store.get(7, task.run_id)


def test_legacy_plan_migrates_against_checkpoint(tmp_path):
    store, task, rev = planned(tmp_path)
    with store._db(write=True) as db:
        db.execute("DELETE FROM plan_seals WHERE task=?", (str(task.run_id),))
    reopened = ResearchStore(tmp_path)
    state, _ = reopened.get(7, task.run_id)
    reopened.save(7, state, rev, "step", "seal-legacy")
    assert reopened.plan_metadata(7, task.run_id)["first_revision"] == rev
    assert json.loads(reopened.checkpoint(7, task.run_id, rev).model_dump_json())["question_plan"]["graph"]
