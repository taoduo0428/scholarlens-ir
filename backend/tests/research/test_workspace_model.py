from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from backend.config import Settings
from backend.research.api import task_budget
from backend.research.provider_adapter import ProviderError
from backend.research.schemas import TaskInput
from backend.research.store import ResearchStore
from backend.research.workspace_model import allowed, propose, reserve


@pytest.mark.parametrize(
    ("depth", "phases"),
    [
        ("standard", ["planning", "analysis"]),
        ("deep", ["planning", "decision", "analysis", "synthesis"]),
    ],
)
def test_durable_model_reservation_matches_profile(tmp_path, depth, phases):
    store = ResearchStore(tmp_path)
    task = TaskInput(goal="Compare two trials", mode="personal_model", depth=depth)
    state, _, _ = store.create(
        1, "k", task, "g", initial_budget=task_budget(task), retrieval_policy="W4"
    )
    state.budget.deadline = datetime.now(timezone.utc) + timedelta(seconds=10)
    for p in phases:
        assert allowed(state, p) and reserve(store, state, p)
        assert not reserve(store, state, p)
    restored = store.get(1, state.run_id)[0]
    assert not reserve(store, restored, "planning")
    assert restored.budget.model_calls_used == len(phases) == state.budget.max_model_calls


def test_schema_validated_semantic_transport():
    settings = replace(
        Settings(),
        ai_personal=True,
        ai_base_url="https://provider.example/v1",
        ai_model="fixture",
        ai_api_key="fixture-test-key",
        ai_protocol="chat_completions",
    )

    def transport(content):
        return httpx.MockTransport(
            lambda req: httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(content)}}]}
            )
        )

    assert propose(settings, "analysis", {}, 3, transport({"labels": []})).labels == []
    with pytest.raises(ProviderError):
        propose(
            settings,
            "synthesis",
            {},
            3,
            transport({"ordered_claim_ids": [], "emphasis": "answer", "grant": "all"}),
        )
