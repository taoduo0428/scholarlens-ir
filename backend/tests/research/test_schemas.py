"""Research input validation at the model and persistence boundaries."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.research.schemas import (
    Budget, Coverage, EvidenceRef, NextAction, ResearchState, Scope, TaskInput,
)


def ref(**changes):
    fields = dict(evidence_id="e1", paper_id="p1", chunk_id="c1",
                  locator="fulltext:chars:3-8", quote_hash="a" * 64,
                  corpus_version="g1", rights="public_corpus", source_kind="indexed_fulltext",
                  field="fulltext", retrieved_at=datetime.now(timezone.utc))
    return EvidenceRef(**(fields | changes))


def state(**changes):
    fields = dict(run_id=uuid4(), user_id=1, task=TaskInput(goal="研究目标"),
                  corpus_generation="g1")
    return ResearchState(**(fields | changes))


@pytest.mark.parametrize("action", [
    {"kind": "search", "subtask_id": "s1", "query": "two"},
    {"kind": "read", "paper_id": "paper", "chunk_ids": ["chunk"], "purpose": "read"},
    {"kind": "extract", "paper_ids": ["paper"], "subtask_id": "s", "slots": ["method"]},
    {"kind": "replan", "missing_slots": ["protocol"], "reason": "missing"},
    {"kind": "finish", "reason": "plateau"},
])
def test_only_typed_actions_roundtrip(action):
    parsed = TypeAdapter(NextAction).validate_python(action)
    assert TypeAdapter(NextAction).validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize("action", [
    {"kind": "shell", "cmd": "unused"},
    {"kind": "finish", "reason": "plateau", "credential": "marker"},
    {"kind": "read", "paper_id": "paper", "chunk_ids": [], "purpose": "read"},
    {"kind": "search", "query": "word", "subtask_id": "s", "strategy": "web"},
    {"kind": "search", "query": "word", "subtask_id": "s", "filters": {"year_from": 2025, "year_to": 2024}},
])
def test_invalid_action_rejected(action):
    with pytest.raises(ValidationError):
        TypeAdapter(NextAction).validate_python(action)


@pytest.mark.parametrize("kwargs", [
    {"max_rounds": 5}, {"max_tool_calls": 31}, {"max_model_calls": 21},
    {"max_evidence": 31}, {"max_duration_seconds": 601}, {"rounds_used": 5},
    {"max_tool_calls": 1, "tool_calls_used": 2}, {"model_calls_used": -1},
    {"model_calls_used": 1, "max_model_calls": 0}, {"cost_estimate": float("nan")},
])
def test_budget_rejects_invalid_limits_and_usage(kwargs):
    with pytest.raises(ValidationError):
        Budget(**kwargs)


@pytest.mark.parametrize("change", [
    {"quote_hash": "g" * 64}, {"locator": "fulltext:page:3"},
    {"locator": "fulltext:chars:8-3"}, {"locator": "fulltext:chars:3-3"},
    {"locator": "title:chars:3-8"},
])
def test_reference_identity_is_bounded_and_locator_agrees_with_field(change):
    with pytest.raises(ValidationError):
        ref(**change)


def test_generation_and_lower_task_evidence_budget():
    first = ref()
    assert state(evidence_refs=[first]).evidence_refs == [first]
    with pytest.raises(ValidationError):
        state(evidence_refs=[ref(corpus_version="g2")])
    with pytest.raises(ValidationError):
        state(budget=Budget(max_evidence=1), evidence_refs=[first, ref(evidence_id="e2")])


def test_unbounded_nested_context_rejected():
    with pytest.raises(ValidationError):
        Coverage(per_subtask={"s": ["method"] * 8})
    with pytest.raises(ValidationError):
        Scope(paper_ids=["p"] * 41)
    with pytest.raises(ValidationError):
        TaskInput(goal="private goal", credential="marker")
