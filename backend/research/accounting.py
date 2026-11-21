"""Summarize actual spending without treating an unknown token count as free usage."""

from collections import Counter


def spending(state):
    calls = Counter(a.tool for a in state.actions)
    plan_calls = state.planning_calls
    total = state.budget.model_calls_used
    return {
        "model_calls": total, "planning_calls": plan_calls, "decision_calls": max(0, total-plan_calls),
        "synthesis_calls": 0, "verification_model_calls": 0,
        "tools": state.budget.tool_calls_used, "max_tools": state.budget.max_tool_calls,
        "retrieval_calls": sum(n for name,n in calls.items() if name != "verify_source_quote"),
        "source_readbacks": calls["verify_source_quote"],
        "failed_calls": sum(a.status == "error" for a in state.actions),
        "evidence_count": len(state.evidence_refs),
        "publication_reserved_before_finish": len(state.evidence_refs) if state.retrieval_policy != "V1" else 0,
        "tokens": 0 if total == 0 else state.budget.tokens_used,
        "cost": 0 if total == 0 else state.budget.cost_estimate,
        "deadline": state.budget.deadline.isoformat() if state.budget.deadline else None,
    }
