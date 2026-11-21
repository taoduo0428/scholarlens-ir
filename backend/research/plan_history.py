"""Record actual question reordering without changing scope, obligations or budget."""

from backend.research.questions import revise


def record_order(state):
    previous = state.question_plan
    if not previous or previous.plan_version >= 4:
        return
    by_id = {n.id: n for n in previous.graph.nodes}
    order = [sub.id for sub in state.subtasks]
    if order == list(by_id) or set(order) != set(by_id):
        return
    nodes = [by_id[key].model_dump() for key in order]
    state.question_plan = revise(previous, {"nodes": nodes},
                                f"Round {state.budget.rounds_used}: dependencies and outstanding evidence prioritize {order[0]}.")
