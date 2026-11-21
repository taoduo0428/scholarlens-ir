"""Typed, local HTTP fixture for exercising the personal-model protocol. No external LLM."""

import json
from dataclasses import replace

import httpx

from backend.config import Settings
from backend.research.provider_adapter import choose_action, plan_questions
from backend.research.questions import ResearchTaskContract, fallback
from backend.research.workspace_model import propose


def adapters():
    settings = replace(
        Settings(),
        ai_personal=True,
        ai_base_url="https://provider.example/v1",
        ai_protocol="chat_completions",
        ai_model="controlled-http/1",
        ai_api_key="controlled-fixture",
    )

    def transport(response):
        def handle(req):
            body = json.loads(req.content)
            assert body["messages"] and body["model"] == settings.ai_model
            return httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(response)}}]}
            )

        return httpx.MockTransport(handle)

    def plan(view, remaining):
        fallback_plan = fallback(ResearchTaskContract.model_validate(view["task"]))
        return plan_questions(
            settings, view, remaining, transport(fallback_plan.model_dump())
        )

    def decide(view, remaining):
        target = next(
            (t for t in view["targets"] if t.get("missing_slots") or t.get("missing")),
            view["targets"][0],
        )
        reply = {
            "kind": "search",
            "subtask_id": target["id"],
            "query": target["goal"][:500],
            "strategy": "keyword",
        }
        return choose_action(settings, view, remaining, transport(reply))

    def review(phase, view, remaining):
        if phase == "analysis":
            labels = [
                {
                    "claim_id": item["id"],
                    "evidence_id": item["sources"][0]["id"],
                    "answer_relation": "premise",
                    "support_span": item["sources"][0]["text"][:80],
                }
                for item in view["claims"]
                if item["sources"]
            ]
            reply = {"labels": labels}
        else:
            reply = {
                "ordered_claim_ids": [item["id"] for item in view["items"]],
                "emphasis": "conditions",
            }
        return propose(settings, phase, view, remaining, transport(reply))

    return {"choose": decide, "question_planner": plan, "semantic": review}
