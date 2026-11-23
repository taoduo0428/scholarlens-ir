"""Bounded, JSON-only contracts shared by the research worker, API and checkpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.research.questions import QuestionPlan
from backend.research.answer_contract import AnswerContract
from backend.research.field_contract import AnswerRequirement

Id = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=192)]
Summary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
SearchMode = Literal["keyword", "semantic", "hybrid"]
Status = Literal["queued", "running", "paused", "awaiting_credentials", "awaiting_input",
                 "completed", "partial", "failed", "cancelled"]
Stop = Literal["complete", "plateau", "budget", "blocked", "cancelled"]
Slot = Literal["fact", "method", "dataset", "metric", "protocol", "limitation", "comparison"]
SourceKind = Literal["indexed_fulltext", "abstract", "metadata", "private_upload", "external_abstract"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, validate_default=True)


class Scope(Contract):
    paper_ids: list[Id] = Field(default_factory=list, max_length=40)
    include_own_uploads: bool = False
    library_only: Literal[True] = True


class ResearchProject(Contract):
    workspace: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
    project: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]


class PdfCellRequest(Contract):
    paper_id: Id
    source_version: Digest
    page: int = Field(ge=1, le=500, strict=True)
    table_id: int = Field(ge=1, le=20, strict=True)
    row: int = Field(ge=1, le=100, strict=True)
    column: int = Field(ge=1, le=40, strict=True)


class TaskInput(Contract):
    pdf_cell: PdfCellRequest | None = Field(default=None, exclude_if=lambda v: v is None)
    research_project: ResearchProject | None = Field(default=None, exclude_if=lambda v: v is None)
    goal: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=3000)]
    scope: Scope = Field(default_factory=Scope)
    depth: Literal["standard", "deep"] = "standard"
    mode: Literal["evidence_only", "personal_model"] = "evidence_only"
    conversation_id: Id | None = None
    constraints: list[Summary] = Field(default_factory=list, max_length=6)
    requested_deliverables: list[Literal["report", "matrix", "sources"]] = Field(
        default_factory=lambda: ["report", "matrix", "sources"], max_length=3
    )

    @model_validator(mode="after")
    def validate_pdf_scope(self):
        if self.pdf_cell and self.pdf_cell.paper_id not in self.scope.paper_ids:
            raise ValueError("PDF cell requires an explicitly scoped paper")
        return self


class SearchFilter(Contract):
    year_from: int | None = Field(None, ge=1, le=9999)
    year_to: int | None = Field(None, ge=1, le=9999)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("reversed year filter")
        return self


class Search(Contract):
    kind: Literal["search"] = "search"
    subtask_id: Id
    query: Summary
    strategy: SearchMode = "keyword"
    filters: SearchFilter = Field(default_factory=SearchFilter)


class Read(Contract):
    kind: Literal["read"] = "read"
    paper_id: Id
    chunk_ids: list[Id] = Field(min_length=1, max_length=12)
    purpose: Summary


class Extract(Contract):
    kind: Literal["extract"] = "extract"
    subtask_id: Id
    paper_ids: list[Id] = Field(min_length=1, max_length=10)
    slots: list[Slot] = Field(min_length=1, max_length=7)


class Replan(Contract):
    kind: Literal["replan"] = "replan"
    missing_slots: list[Slot] = Field(min_length=1, max_length=7)
    reason: Summary


class Finish(Contract):
    kind: Literal["finish"] = "finish"
    reason: Literal["complete", "plateau", "budget", "blocked"]


NextAction = Annotated[Search | Read | Extract | Replan | Finish, Field(discriminator="kind")]


class Decision(Contract):
    decision_id: UUID
    model_version: Id
    policy_version: Id
    input_state_hash: Digest
    explanation_summary: Summary
    action: NextAction


class Subtask(Contract):
    id: Id
    goal: Summary
    required_slots: list[Slot] = Field(min_length=1, max_length=7)
    missing_slots: list[Slot] = Field(default_factory=list, max_length=7)
    status: Literal["pending", "active", "satisfied", "blocked"] = "pending"
    priority: int = Field(default=1, ge=1, le=6)


class Query(Contract):
    subtask_id: Id
    query: Summary
    mode: SearchMode
    attempted: bool
    result_summary: Summary
    exhausted_search: Digest | None = Field(default=None, exclude_if=lambda value: value is None)


class EvidenceRef(Contract):
    evidence_id: Id
    paper_id: Id
    chunk_id: Id
    locator: Annotated[str, StringConstraints(
        max_length=64, pattern=r"^(title|abstract|fulltext):chars:[0-9]+-[0-9]+$"
    )]
    quote_hash: Digest
    corpus_version: Id
    rights: Literal["public_corpus", "owner_only", "licensed_metadata"]
    source_kind: SourceKind
    field: Literal["title", "abstract", "fulltext"]
    retrieved_at: datetime

    @model_validator(mode="after")
    def valid_locator(self):
        field, _, offsets = self.locator.split(":")
        start, end = map(int, offsets.split("-"))
        if field != self.field or start >= end:
            raise ValueError("field and nonempty character interval must match locator")
        return self


class Conditions(Contract):
    dataset: Summary | None = None
    metric_name: Summary | None = None
    metric_value: Annotated[str, StringConstraints(max_length=80)] | None = None
    unit: Id | None = None
    experiment_setup: Summary | None = None
    evaluation_protocol: Summary | None = None


class Claim(Contract):
    claim_id: Id
    subtask_id: Id
    statement: Summary
    claim_type: Literal["fact", "method", "metric", "comparison", "limitation"]
    support_status: Literal["verified", "contradicted", "insufficient", "unverified", "not_comparable"]
    paper_ids: list[Id] = Field(default_factory=list, max_length=10)
    evidence_ids: list[Id] = Field(default_factory=list, max_length=12)
    conditions: Conditions = Field(default_factory=Conditions)
    verifier_version: Id
    check_notes: list[Summary] = Field(default_factory=list, max_length=5)


class Coverage(Contract):
    per_subtask: dict[Id, Annotated[list[Slot], Field(max_length=7)]] = Field(
        default_factory=dict, max_length=6
    )
    missing: list[Slot] = Field(default_factory=list, max_length=7)
    conflict: list[Id] = Field(default_factory=list, max_length=30)
    source_diversity: int = Field(default=0, ge=0, le=30)


class ActionRecord(Contract):
    seq: int = Field(ge=1)
    tool: Id
    tool_execution_id: Id
    input_digest: Digest
    output_digest: Digest | None = None
    status: Literal["done", "empty", "error", "denied"]
    elapsed_ms: int = Field(ge=0)
    error_code: Id | None = None


class Budget(Contract):
    max_rounds: int = Field(default=4, ge=1, le=4)
    max_tool_calls: int = Field(default=30, ge=1, le=30)
    max_model_calls: int = Field(default=20, ge=0, le=20)
    max_evidence: int = Field(default=30, ge=1, le=30)
    max_duration_seconds: int = Field(default=600, ge=1, le=600)
    rounds_used: int = Field(default=0, ge=0)
    tool_calls_used: int = Field(default=0, ge=0)
    model_calls_used: int = Field(default=0, ge=0)
    tokens_used: int | None = Field(default=None, ge=0)
    cost_estimate: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    deadline: AwareDatetime | None = None

    @model_validator(mode="after")
    def check_usage(self):
        for used, maximum in [(self.rounds_used, self.max_rounds),
                              (self.tool_calls_used, self.max_tool_calls),
                              (self.model_calls_used, self.max_model_calls)]:
            if used > maximum:
                raise ValueError("budget exceeded")
        return self


class ResearchState(Contract):
    run_id: UUID
    user_id: int = Field(gt=0)
    status: Status = "queued"
    task: TaskInput
    corpus_generation: Id
    model_id: Id = "none"
    pra_arm: Literal["A", "B", "C", "D", "E", "F", "G"] = "A"
    skill_version: Id = "baseline-v1"
    harness_policy_version: Id = "bounded-v1"
    subtasks: list[Subtask] = Field(default_factory=list, max_length=6)
    queries: list[Query] = Field(default_factory=list, max_length=30)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=30)
    claims: list[Claim] = Field(default_factory=list, max_length=60)
    coverage: Coverage = Field(default_factory=Coverage)
    actions: list[ActionRecord] = Field(default_factory=list, max_length=30)
    decisions: list[Decision] = Field(default_factory=list, max_length=30)
    budget: Budget = Field(default_factory=Budget)
    retrieval_policy: Literal["V1", "V2", "V3", "V4", "V5", "V6", "V7", "W4", "E9", "E9.1", "E10", "E11"] = "V1"
    field_requirements: list[AnswerRequirement] = Field(default_factory=list, max_length=6)
    evidence_questions: dict[Id, Id] = Field(default_factory=dict, max_length=30)
    question_reads: dict[Id,list[Id]] = Field(default_factory=dict,max_length=6)
    question_plan: QuestionPlan | None = None
    answer_contract: AnswerContract | None = None
    workspace_trace: list[dict] = Field(default_factory=list, max_length=30)
    reasoning_calls: dict[str, int] = Field(default_factory=dict, max_length=5)
    planning_calls: int = Field(default=0, ge=0, le=20)
    question_assessments: dict[Id, dict] = Field(default_factory=dict, max_length=6)
    skill_steps: list[Id] = Field(default_factory=list, max_length=4)
    candidate_papers: list[Id] = Field(default_factory=list, max_length=40)
    checkpoint_ref: Id | None = None
    artifact_refs: list[Id] = Field(default_factory=list, max_length=120)
    warnings: list[Summary] = Field(default_factory=list, max_length=20)
    stop_reason: Stop | None = None

    @model_validator(mode="after")
    def verify_evidence_bindings(self):
        if len(self.evidence_refs) > self.budget.max_evidence:
            raise ValueError("evidence budget exceeded")
        if any(ref.corpus_version != self.corpus_generation for ref in self.evidence_refs):
            raise ValueError("evidence generation mismatch")
        return self
