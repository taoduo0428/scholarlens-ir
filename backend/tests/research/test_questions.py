from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.research.questions import Blueprint, bind, classify, make_plan, revise
from backend.research.schemas import ResearchState, Scope, TaskInput


def state(goal="比较两个系统在相同测试条件下的延迟。"):
    return ResearchState(run_id=UUID(int=1), user_id=1, corpus_generation="fixture:optics",
                         task=TaskInput(goal=goal, scope=Scope(paper_ids=["p1", "p2"])))


@pytest.mark.parametrize(("text", "intent"), [
    ("How many observations were recorded?", "fact"), ("比较旋转与平移的测量", "comparison"),
    ("为何这些研究结果矛盾？", "conflicting_findings"), ("Trace the causal mechanism", "multihop"),
    ("梳理压缩算法的技术脉络", "landscape"), ("Can this result guarantee uptime?", "insufficient")])
def test_intent(text, intent):
    assert classify(text) == intent


def test_cycle_missing_prerequisite_and_source_escape_are_rejected():
    plan = make_plan(state())
    data = plan.graph.model_dump()
    data["nodes"][0]["dependencies"] = ["q3"]
    with pytest.raises(ValidationError):
        Blueprint.model_validate(data)
    data = plan.graph.model_dump()
    data["nodes"][-1]["dependencies"] = []
    with pytest.raises(ValidationError):
        bind(plan.contract, data)
    data = plan.graph.model_dump()
    data["nodes"][0]["question"] += " source-sha256:" + "a" * 64
    with pytest.raises(ValueError, match="outside_scope"):
        bind(plan.contract, data)


def test_model_repair_and_revisions():
    s = state()
    valid = make_plan(s).graph.model_dump()
    called = []
    def choose(contract, errors):
        called.append(list(errors))
        return {} if not errors else valid
    plan = make_plan(s, choose)
    assert called == [[], ["invalid_plan"]] and plan.origin == "personal_model"
    changed = plan.graph.model_dump()
    changed["nodes"][0]["question"] += "（补充原文定位）"
    updated = revise(plan, changed, "需要定位第一个实验的来源")
    assert updated.plan_version == 2 and updated.contract == plan.contract
    assert plan.plan_version == 1


def test_invalid_proposals_fallback_and_are_bounded():
    calls = []
    def propose(*_):
        calls.append(True)
        return {"tools": ["made up"]}
    plan = make_plan(state(), propose)
    assert plan.origin == "deterministic_fallback" and len(calls) == 2
    assert plan.input_hash and len(plan.prompt_hash) == 64
