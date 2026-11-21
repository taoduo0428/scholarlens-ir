import pytest
from pydantic import ValidationError

from backend.research.skills.program import compile_program
from tools.research_eval.agent_ablation import gate
from tools.research_evolution.evaluate_skill import verified_program


def test_untrusted_skill_and_trace_tampering_are_rejected():
    program = compile_program({"schema": "accepted-public-traces-v1", "category_counts": {"metrics": 2},
                               "dataset_version": "a" * 64, "trace_hashes": ["b"*64]})
    data = program.model_dump()
    with pytest.raises(ValidationError):
        verified_program({**data, "steps": ["arbitrary_tool"]}, program)
    with pytest.raises(ValueError, match="reproduce"):
        verified_program({**data, "trace_hashes": ["f"*64]}, program)


def test_reduced_cost_cannot_hide_negative_transfer():
    base = dict(source_errors=0, outside_scope=0, tool_errors=0, hit=4, negative_with_verified_claim=0, tools=20, p95_ms=500)
    assert "abstention_regression" in gate(base, {**base, "tools": 4, "negative_with_verified_claim": 1})
    assert "no_demonstrated_gain" in gate(base, base)
    assert "outside_scope" in gate(base, {**base, "hit": 6, "outside_scope": 1})
