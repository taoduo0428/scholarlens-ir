from dataclasses import replace
from uuid import UUID

import httpx
import pytest

from backend.config import Settings
from backend.research.accounting import spending
from backend.research.provider_adapter import ProviderError, plan_questions
from backend.research.questions import make_plan
from backend.research.schemas import ResearchState, TaskInput
from backend.research.store import Conflict, ResearchStore


def test_legacy_state_and_pinned_policy(tmp_path):
    task = TaskInput(goal="Which effects were measured?")
    old = {"run_id": str(UUID(int=15)), "user_id": 1, "task": task.model_dump(), "corpus_generation": "g"}
    loaded = ResearchState.model_validate(old)
    assert loaded.retrieval_policy == "V1" and loaded.question_plan is None
    assert spending(loaded)["cost"] == 0
    store = ResearchStore(tmp_path)
    state, rev, _ = store.create(1, "pin", task, "g", retrieval_policy="V3")
    state.retrieval_policy = "V5"
    with pytest.raises(Conflict, match="immutable"):
        store.save(1, state, rev, "started", "new")


def test_controlled_http_planner_rejects_rate_limit_and_validates_json():
    import json

    state = ResearchState(run_id=UUID(int=1), user_id=1, task=TaskInput(goal="Compare two spectra"), corpus_generation="g")
    graph = make_plan(state).graph
    settings = replace(Settings(), ai_api_key="unit-fixture-token", ai_base_url="https://provider.example/v1",
                       ai_protocol="chat_completions", ai_model="fixture", ai_personal=True)
    payload = {"choices":[{"message":{"content":json.dumps(graph.model_dump())}}]}
    def controlled(request):
        body = json.loads(request.content)
        assert "scope" in body["messages"][0]["content"]
        return httpx.Response(200, json=payload)
    assert plan_questions(settings, {"task":"compare"}, 3, httpx.MockTransport(controlled)) == graph
    with pytest.raises(ProviderError, match="rate_limited"):
        plan_questions(settings, {}, 2, httpx.MockTransport(lambda _: httpx.Response(429)))
