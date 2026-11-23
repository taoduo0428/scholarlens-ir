from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import httpx
import pytest

from backend.config import Settings
from backend.research.api import task_budget
from backend.research.provider_adapter import ProviderError
from backend.research.schemas import TaskInput
from backend.research.store import ResearchStore
from backend.research.workspace_model import allowed, propose, reserve


def test_review_uses_actual_visible_claim_and_evidence_pairs(monkeypatch):
    from backend.research import workspace_model as model

    sentence = "We used the recorded observations to evaluate the model."
    quote = "前文。" * 225 + sentence + " Afterward we performed another trial."
    claims = [SimpleNamespace(claim_id=str(i), statement=sentence, evidence_ids=["main", "extra", "hidden"])
              for i in range(13)]
    state = SimpleNamespace(claims=claims, retrieval_policy="W4", task=SimpleNamespace(goal="Which observations?"))
    sources = {key: {"quote": quote} for key in claims[0].evidence_ids}

    def stage(store, state, callback, phase, payload):
        if phase == "synthesis":
            assert [i["id"] for i in payload["items"]] == [str(i) for i in range(12)]
            return model.Narrative(ordered_claim_ids=["12", "1", "1"], emphasis="answer")
        view = payload["claims"][0]["sources"][0]["text"]
        assert len(view) == 560 and view in quote and sentence in view
        labels = [model.SemanticLabel(claim_id=cid, evidence_id=eid, answer_relation="responsive",
                                      support_span=sentence) for cid, eid in
                  [("0", "main"), ("1", "hidden"), ("12", "main")]]
        return model.Review(labels=labels)

    monkeypatch.setattr(model, "semantic_call", stage)
    labels, reviewable = model.publication_suggestions(None, state, sources, object())
    order = model.synthesis_order(None, state, reviewable, object())
    assert labels == {"0": "responsive"}
    assert order == ["1"]


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
