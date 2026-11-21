"""Build the bounded model view from task state; excerpts and credentials stay out."""
from backend.research.schemas import ResearchState


def working_context(state: ResearchState, threshold: int = 8) -> dict:
    if state.retrieval_policy in {"V5", "V6", "V7"}:
        from backend.research.context_layers import layered

        return layered(state)
    recent = max(1, min(threshold, 12))
    return {
        "goal": state.task.goal,
        "scope": state.task.scope.model_dump(),
        "targets": [{"id": s.id, "goal": s.goal, "missing_slots": s.missing_slots}
                    for s in state.subtasks],
        "queries": [q.model_dump() for q in state.queries[-recent:]],
        "evidence": [{"id": e.evidence_id, "paper": e.paper_id, "locator": e.locator}
                     for e in state.evidence_refs],
        "coverage": state.coverage.model_dump(),
        "remaining": {"tools": state.budget.max_tool_calls - state.budget.tool_calls_used,
                      "rounds": state.budget.max_rounds - state.budget.rounds_used},
    }
