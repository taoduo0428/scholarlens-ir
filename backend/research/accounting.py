"""Summarize actual spending without treating an unknown token count as free usage."""

from collections import Counter


def spending(state, receipts=()):
    calls = Counter(a.tool for a in state.actions)
    plan_calls = state.planning_calls
    total = state.budget.model_calls_used
    measured = len(receipts)

    def summed(key):
        if total == 0 and not measured:
            return 0
        if measured != total or any(row[key] is None for row in receipts):
            return None
        return sum(row[key] for row in receipts)

    input_tokens, output_tokens = summed("input_tokens"), summed("output_tokens")
    tokens = input_tokens + output_tokens if None not in (input_tokens, output_tokens) else None
    return {
        "provider_receipts": measured, "model": state.model_id,
        "providers": sorted({row["provider"] for row in receipts}),
        "input_tokens": input_tokens, "output_tokens": output_tokens, "cached_tokens": summed("cached_tokens"),
        "provider_latency_ms": sum(row["latency_ms"] for row in receipts) if receipts else None,
        "model_calls": total, "planning_calls": plan_calls, "decision_calls": state.reasoning_calls.get("decision", 0) if state.answer_contract else max(0, total-plan_calls),
        "synthesis_calls": state.reasoning_calls.get("synthesis", 0), "verification_model_calls": state.reasoning_calls.get("analysis", 0),
        "tools": state.budget.tool_calls_used, "max_tools": state.budget.max_tool_calls,
        "retrieval_calls": sum(n for name,n in calls.items() if name != "verify_source_quote"),
        "source_readbacks": calls["verify_source_quote"],
        "failed_calls": sum(a.status == "error" for a in state.actions),
        "evidence_count": len(state.evidence_refs),
        "publication_reserved_before_finish": len(state.evidence_refs) if state.retrieval_policy != "V1" else 0,
        "tokens": tokens if tokens is not None else state.budget.tokens_used,
        "cost": 0 if total == 0 else state.budget.cost_estimate,
        "deadline": state.budget.deadline.isoformat() if state.budget.deadline else None,
    }
