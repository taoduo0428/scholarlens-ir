"""Immutable proof requirements derived from the user's task and the accepted question DAG."""

from hashlib import sha256
import json
import re
from typing import Literal

from pydantic import Field

from backend.research.questions import Need, QuestionPlan, Strict

AnswerKind = Literal[
    "quoted_text",
    "measurement",
    "fact",
    "methods",
    "aligned_comparison",
    "causal_chain",
    "disagreement",
    "availability",
    "overview",
]


class Obligation(Strict):
    id: str
    question_id: str
    need: Need
    requirement: str
    evidence: list[str] = Field(min_length=1, max_length=6)
    prerequisites: list[str] = Field(max_length=5)
    min_papers: int = Field(ge=1, le=3)


class AnswerContract(Strict):
    version: Literal["answer/1"] = "answer/1"
    goal: str
    intent: str
    answer_type: AnswerKind
    constraints: list[str]
    deliverables: list[str]
    scope: dict
    corpus_generation: str
    budget: dict
    binding: str
    obligations: list[Obligation]
    comparison_conditions: list[str]
    stop_conditions: list[str]


def answer_type(plan):
    goal = re.sub(r'["“《][^"”》]+["”》]', " ", plan.contract.goal_original.casefold())
    if plan.contract.intent == "fact" and re.search(
        r"first (?:complete )?sentence|opening sentence|首句|第一句", goal
    ):
        return "quoted_text"
    intent = plan.contract.intent
    if intent in {"literature_synthesis", "trend_analysis"}:
        return "overview"
    if intent == "performance_ranking":
        return "aligned_comparison"
    if intent == "comparison":
        return (
            "methods"
            if re.search(r"approach|method|方法", goal)
            and not re.search(r"metric|protocol|unit|accuracy|指标|协议", goal)
            else "aligned_comparison"
        )
    if (
        re.search(r"\bhow (?:many|much)\b|voltage|temperature|电流|电压|温度|多少", goal)
        and intent == "fact"
    ):
        return "measurement"
    return {
        "comparison": "aligned_comparison",
        "multihop": "causal_chain",
        "conflicting_findings": "disagreement",
        "landscape": "overview",
        "insufficient": "availability",
    }.get(intent, "fact")


def bind_answer(plan: QuestionPlan) -> AnswerContract:
    task = plan.contract
    kind = answer_type(plan)
    requirements = {
        "source_fact": ["authenticated passage", "responsive proposition"],
        "mechanism": ["explicit cause", "explicit effect", "source linking both"],
        "conditions": ["dataset", "metric", "unit", "experimental setup", "evaluation protocol"],
        "comparison": ["two distinct papers", "aligned conditions", "supported comparison"],
        "synthesis": ["supported premises", "traceable conclusion"],
        "availability": ["explicit source for requested field"],
    }
    criteria = {}
    if kind == "methods":
        requirements.update(
            conditions=["explicit method attribution for each scoped paper"],
            comparison=["two distinct papers", "source-bound method descriptions", "no ranking"],
        )
        criteria.update(
            conditions="Attribute each method to its paper and retained passage.",
            comparison="Compare the source-bound descriptions without ranking performance.",
        )
    if kind == "disagreement":
        criteria.update(
            comparison="Locate opposed statements about the same proposition under aligned conditions."
        )
    by_id = {n.id: n for n in plan.graph.nodes}
    # Every required question is bound, even when a provider supplies a different rendering.
    obligations = [
        Obligation(
            id="o-" + n.id,
            question_id=n.id,
            need=n.requirement.kind,
            requirement=criteria.get(n.requirement.kind, n.requirement.acceptance),
            evidence=requirements[n.requirement.kind],
            prerequisites=["o-" + d for d in n.dependencies if d in by_id],
            min_papers=n.requirement.min_papers,
        )
        for n in by_id.values()
    ]
    payload = {
        "task": task.model_dump(),
        "needs": [o.model_dump() for o in obligations],
        "type": kind,
    }
    ident = sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return AnswerContract(
        goal=task.goal_original,
        intent=task.intent,
        answer_type=kind,
        constraints=task.constraints,
        deliverables=task.deliverable,
        scope=task.scope,
        corpus_generation=task.corpus_generation,
        budget=task.budget,
        binding=ident,
        obligations=obligations,
        comparison_conditions=requirements["conditions"]
        if kind in {"aligned_comparison", "disagreement", "methods"}
        else [],
        stop_conditions=[
            "unmet_proof",
            "unresolved_contradiction",
            "incomparable_conditions",
            "source_changed",
            "budget_or_plateau",
        ],
    )
