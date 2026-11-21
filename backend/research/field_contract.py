"""Versioned server-side answer requirements and source capabilities for E9."""

from enum import Enum
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class AnswerFieldType(str, Enum):
    text = "text"
    integer = "integer"
    decimal = "decimal"
    percentage = "percentage"
    metric = "metric"
    date = "date"
    page_number = "page_number"
    bounding_box = "bounding_box"
    table_cell = "table_cell"
    figure_reference = "figure_reference"
    entity = "entity"
    relationship = "relationship"
    list = "list"


Capability = Literal["text", "metadata", "measurement", "page", "geometry", "table", "figure"]
Status = Literal[
    "answerable",
    "partially_answerable",
    "insufficient_evidence",
    "unavailable_in_scope",
    "source_capability_mismatch",
    "conflicted",
    "not_comparable",
    "blocked_by_permission",
]
Reason = Literal[
    "verified",
    "information_not_found",
    "insufficient_evidence",
    "source_capability_mismatch",
    "unavailable_in_scope",
    "blocked_by_permission",
    "conflicted",
    "not_comparable",
    "dependency_open",
]


class RequiredSourceCapability(StrictRecord):
    requires: Capability


class AnswerField(StrictRecord):
    field_id: str
    question_id: str
    request: str = Field(min_length=1, max_length=2200)
    subject: str | None = Field(default=None, max_length=140, exclude_if=lambda v: v is None)
    facet: Literal["unit", "representation", "objective", "trend", "setting", "limitations", "method", "dataset", "metric", "finding", "topic", "conditions", "overview", "comparison", "chain", "conflict"] | None = None
    paper_ids: list[str] = Field(default_factory=list, max_length=50)
    requested_metric: str | None = None
    datatype: AnswerFieldType
    capability: RequiredSourceCapability
    operation: Literal[
        "quote",
        "attribute",
        "fact",
        "measure",
        "compare",
        "method",
        "chain",
        "disagreement",
        "condition",
        "synthesize",
        "layout",
    ]
    min_evidence: int = Field(ge=1, le=4)
    min_papers: int = Field(ge=1, le=4)
    conditions: list[str]
    acceptance: str
    missing_action: Literal["read_authorized_passages", "request_qualified_source"]


class AnswerRequirement(StrictRecord):
    version: Literal["answer-field/1"] = "answer-field/1"
    contract_binding: str
    original_goal: str | None = None
    node_question: str | None = None
    question_id: str
    dependencies: list[str]
    fields: list[AnswerField] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def ownership(self):
        if any(f.question_id != self.question_id for f in self.fields) or len(
            {f.field_id for f in self.fields}
        ) != len(self.fields):
            raise ValueError("invalid field ownership")
        return self


class SourceLocator(StrictRecord):
    paper_id: str
    raw: str
    field: Literal["title", "abstract", "fulltext"]
    start: int = Field(ge=0)
    end: int = Field(ge=1)


class SourceQuality(StrictRecord):
    version: str
    quote_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    verification: Literal["original_slice"] = "original_slice"


class SourceCapability(StrictRecord):
    locator: SourceLocator
    quality: SourceQuality
    supported: list[Capability]


class SourceCoverage(StrictRecord):
    scope: list[str]
    represented: list[str]
    searches: int = Field(ge=0)
    # Retrieval windows establish partial coverage only. A future enumerating corpus
    # adapter can provide a closed-world receipt for a specific field.
    exhaustive: bool = False
    permission_denied: bool = False


class EvidenceBinding(StrictRecord):
    binding_version: Literal["field-binding/1"] = "field-binding/1"
    question_id: str
    field_id: str
    claim_id: str
    evidence_id: str
    acquired_by: str
    relation: Literal["direct", "premise"]
    source_scope: Literal["public_corpus", "owner_only", "licensed_metadata"]
    locator: SourceLocator
    source_version: str
    verification_status: Literal["verified"] = "verified"


class AnswerabilityDecision(StrictRecord):
    field_id: str
    question_id: str
    status: Status
    reason: Reason
    bindings: list[EvidenceBinding]
    next_action: Literal[
        "publish",
        "retrieve",
        "read_layout",
        "align_conditions",
        "resolve_conflict",
        "request_permission",
        "stop",
    ]
    coverage: SourceCoverage


LAYOUT = (
    (r"bounding.box|coordinates?|坐标|边界框", "bounding_box", "geometry"),
    (r"page number|which page|页码|第几页", "page_number", "page"),
    (r"table cell|单元格", "table_cell", "table"),
    (r"figure (?:number|reference)|which figure|图号", "figure_reference", "figure"),
)
PATTERNS = (
    (r"percent|百分|%", "percentage"),
    (r"how many|count|数量|多少个", "integer"),
    (r"\bdate\b|when|日期", "date"),
    (r"\blist\b|列出", "list"),
    (r"which (?:entity|institution|author)|who|机构|作者", "entity"),
    (r"accuracy|recall|precision|metric|指标|准确率", "metric"),
    (r"how much|temperature|voltage|current|weight|decimal|温度|电压|电流", "decimal"),
)
TITLES = re.compile(r'["“《][^"”》]+["”》]')


def requests(goal):
    quoted = []

    def mask(m):
        quoted.append(m[0])
        return f"@TITLE{len(quoted) - 1}@"

    masked = TITLES.sub(mask, goal)
    masked = re.sub(r"[，,]?\s*(?:并据此|再|然后|并)(?=解释|分析|推断)", "；", masked)
    parts = re.split(
        r"\s+(?:and|then)\s+(?=(?:give|provide|identify|state|list|report|name|what|which|how|find|quote)\b)|[?？;；]\s*(?=\S)|(?:并且|并)(?=给出|提供|列出|报告|说明)",
        masked,
        flags=re.I,
    )
    if len(parts) == 1:
        compound = re.fullmatch(
            r"(what (?:is|are) (?:the )?)([\w -]+?) and ([\w -]+?) (of|for) (.+?)[?.]?",
            masked,
            re.I,
        )
        if compound:
            parts = [
                f"What is the {noun} {compound[4]} {compound[5]}?"
                for noun in (compound[2], compound[3])
            ]
    if len(parts) > 16:
        parts = [masked]  # Keep an oversized compound unresolved as one full request.
    return [
        re.sub(
            r"@TITLE(\d+)@",
            lambda m: quoted[int(m[1])] if int(m[1]) < len(quoted) else m[0],
            p.strip(),
        )
        for p in parts
        if p.strip()
    ]


def field_for(node, contract, request, ordinal):
    kind = node.requirement.kind
    goal = TITLES.sub("", request).casefold()
    data_type, cap, operation = "text", "text", "fact"
    conditions = []
    if len(contract.obligations) > 1:
        operation = {
            "source_fact": "fact",
            "conditions": "condition",
            "comparison": "compare",
            "mechanism": "chain",
            "synthesis": "synthesize",
            "availability": "fact",
        }[kind]
        if contract.answer_type == "methods" and kind in {
            "conditions",
            "comparison",
            "source_fact",
        }:
            operation = "method"
        elif contract.answer_type == "disagreement" and kind in {
            "conditions",
            "comparison",
            "synthesis",
        }:
            operation = "disagreement"
        if operation in {"condition", "compare"}:
            data_type, cap, conditions = (
                "metric",
                "measurement",
                ["metric_name", "dataset", "unit", "experiment_setup", "evaluation_protocol"],
            )
        elif operation in {"method", "chain", "disagreement", "synthesize"}:
            data_type = "relationship"
    else:
        layout = next(((t, c) for pattern, t, c in LAYOUT if re.search(pattern, goal)), None)
        if layout:
            data_type, cap = layout
            operation = "layout"
        elif re.search(r"first (?:complete )?sentence|opening sentence|首句|第一句|开篇原句|开头一句", goal):
            operation = "quote"
        else:
            data_type = next((t for pattern, t in PATTERNS if re.search(pattern, goal)), "text")
            operation = (
                "measure"
                if data_type in {"integer", "decimal", "percentage", "metric"}
                else "attribute"
            )
            cap = "measurement" if operation == "measure" else "text"
    return AnswerField(
        field_id=f"{node.id}.f{ordinal}",
        question_id=node.id,
        request=request,
        datatype=AnswerFieldType(data_type),
        operation=operation,
        capability=RequiredSourceCapability(requires=cap),
        min_evidence=node.requirement.min_papers,
        min_papers=node.requirement.min_papers,
        conditions=conditions,
        acceptance=f"Bind {data_type} to the requested {operation} in authorized source passages.",
        missing_action="request_qualified_source"
        if operation == "layout"
        else "read_authorized_passages",
    )


def requirements(plan, contract):
    result = []
    for node in plan.graph.nodes:
        pieces = requests(contract.goal) if len(plan.graph.nodes) == 1 else [contract.goal]
        result.append(
            AnswerRequirement(
                contract_binding=contract.binding,
                question_id=node.id,
                dependencies=node.dependencies,
                fields=[field_for(node, contract, p, i) for i, p in enumerate(pieces, 1)],
            )
        )
    return result
