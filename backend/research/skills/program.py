"""Offline-only, finite research procedures with a closed set of typed operations."""

from hashlib import sha256
import json
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from backend.research.questions import Intent, Strict

Hash = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Operation = Literal["identify_comparators", "collect_conditions", "target_missing_paper", "locate_mechanism"]


class ResearchSkillSpec(Strict):
    schema_version: Literal["research-skill/1"] = "research-skill/1"
    parent: Literal["baseline-v1"] = "baseline-v1"
    intents: list[Intent] = Field(min_length=1, max_length=3)
    min_papers: int = Field(ge=1, le=3)
    steps: list[Operation] = Field(min_length=1, max_length=4)
    on_missing: Literal["record_gap"] = "record_gap"
    expected: Literal["condition_matrix", "mechanism_evidence"]
    dataset_hash: Hash
    trace_hashes: list[Hash] = Field(min_length=1, max_length=128)
    status: Literal["candidate"] = "candidate"

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.steps)) != len(self.steps) or len(set(self.trace_hashes)) != len(self.trace_hashes):
            raise ValueError("duplicate instruction or source")
        return self

    @property
    def version(self):
        raw = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":")).encode()
        return "rs-" + sha256(raw).hexdigest()[:20]


def compile_program(analysis):
    if analysis["schema"] != "accepted-public-traces-v1":
        raise ValueError("unverified public training set")
    count = analysis["category_counts"]
    compare = sum(count.get(k, 0) for k in ("metrics", "comparison", "incomparable")) > 0
    return ResearchSkillSpec(intents=["comparison", "conflicting_findings"] if compare else ["multihop"],
        min_papers=2 if compare else 1,
        steps=["identify_comparators", "collect_conditions", "target_missing_paper"] if compare else ["locate_mechanism"],
        expected="condition_matrix" if compare else "mechanism_evidence",
        dataset_hash=analysis["dataset_version"], trace_hashes=sorted(analysis["trace_hashes"]))


def interpret(program, state):
    """Only retrieval hints/target subsets can leave this interpreter. No tool executes here."""
    plan = state.question_plan
    scope = state.task.scope.paper_ids
    if plan.contract.intent not in program.intents or len(scope) < program.min_papers:
        return "", [], []
    hints, targets, executed = [], [], []
    for operation in program.steps:
        if operation == "identify_comparators":
            hints.append("compared methods baseline comparator")
        elif operation == "collect_conditions":
            hints.append("dataset evaluation protocol metric unit experimental setup")
        elif operation == "target_missing_paper":
            covered = {e.paper_id for e in state.evidence_refs}
            if covered:
                targets = [pid for pid in scope if pid not in covered]
        elif operation == "locate_mechanism":
            hints.append("procedure mechanism underlying explanation")
        executed.append(operation)
    return " ".join(hints), targets, executed
