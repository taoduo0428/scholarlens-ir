"""Server-owned capability contracts for every research tool."""
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Output(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Papers(Output):
    papers: list[dict]


class Passages(Output):
    passages: list[dict]


class Paper(Output):
    paper: dict


class Cell(Output):
    source_scope: Literal["owner_only", "public_corpus"]
    paper_id: str
    source_version: str
    page: int
    table_id: int
    row: int
    column: int
    locator: str
    bbox: list[float]
    quote: str
    quote_sha256: str


class Verification(Output):
    verified: bool
    reason: str


class Extraction(Output):
    slots: dict[str, list[dict]]


class TaskView(Output):
    run_id: str
    status: str
    coverage: dict
    budget: dict
    stop_reason: str | None


OUTPUTS = MappingProxyType({
    "read_pdf_cell": Cell,
    "search_papers": Papers, "search_passages": Passages, "read_paper_metadata": Paper,
    "read_paper_chunks": Passages, "verify_source_quote": Verification,
    "extract_method_results": Extraction, "get_research_state": TaskView,
})


def timeout_for(name):
    return {"search_papers": 20, "search_passages": 25, "read_pdf_cell": 15}.get(name, 10)


def describe():
    from backend.research.tools.registry import REQUESTS
    return [{"tool_id": tool, "input_schema": schema.model_json_schema(),
             "output_schema": OUTPUTS[tool].model_json_schema(), "risk": "read_only",
             "permission": "task:read" if tool == "get_research_state" else "paper:read",
             "side_effect": "none", "idempotent": True, "automatic_retries": 0,
             "timeout_seconds": timeout_for(tool)} for tool, schema in REQUESTS.items()]
