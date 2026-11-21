from uuid import UUID

from backend.research.context_layers import encoded, layered
from backend.research.schemas import ResearchState, Scope, TaskInput


def test_compaction_caps_bytes_and_keeps_original_scope_and_goal():
    ids = [f"paper-{i}-" + "z"*150 for i in range(40)]
    state = ResearchState(run_id=UUID(int=1), user_id=3, corpus_generation="fixture:context",
                         task=TaskInput(goal="比"*2200, scope=Scope(paper_ids=ids)))
    context = layered(state, 4000)
    assert len(encoded(context)) <= 4000 and context["omitted"]["scope_or_goal_truncated"]
    assert state.task.scope.paper_ids == ids and len(state.task.goal) == 2200
    other = state.model_copy(update={"user_id": 4})
    assert layered(other, 4000)["namespace"] != context["namespace"]
