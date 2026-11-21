"""Record an explicitly selected physical PDF cell using the task's authorized registry."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from subprocess import TimeoutExpired
from time import monotonic

from backend.research.harness import call_tool
from backend.research.pdf_layout import from_path
from backend.research.schemas import ActionRecord
from backend.research.store import canonical, digest
from backend.research.tools.passages import ToolError
from backend.research.tools.sources import private_doc


def read_cell(req, doc, resolver):
    if doc.get("_rights") == "licensed_metadata":
        raise ToolError("pdf_not_available")
    path = resolver(doc) if resolver else None
    if not path:
        raise ToolError("pdf_not_available")
    try:
        page = from_path(Path(path), req.paper_id, req.page)
    except RuntimeError:
        raise ToolError("layout_dependency_unavailable") from None
    except (ValueError, OSError, TimeoutExpired):
        raise ToolError("layout_unavailable") from None
    if page["source_version"] != req.source_version or page["page"] != req.page or page["paper_id"] != req.paper_id:
        raise ToolError("layout_version_mismatch")
    cells = [item for item in page["items"] if item["kind"] == "cell" and
             (item["table_id"], item["row"], item["column"]) == (req.table_id, req.row, req.column)]
    if len(cells) != 1 or not cells[0]["quote"].strip():
        raise ToolError("cell_not_found")
    cell = cells[0]
    raw = cell["quote"]
    if sha256(raw.encode()).hexdigest() != cell["quote_sha256"]:
        raise ToolError("layout_hash_mismatch")
    return {**req.model_dump(), "source_scope": "owner_only" if private_doc(doc) else "public_corpus",
            "quote":raw, "quote_sha256":cell["quote_sha256"],
            "locator":cell["locator"], "bbox":list(cell["bbox"])}


def publish_cell(state, registry):
    request = state.task.pdf_cell
    args = request.model_dump()
    if (registry is None or registry.owner_id != state.user_id or registry.scope != state.task.scope
            or registry.generation != state.corpus_generation):
        return {"status":"unavailable", "reason":"report_source_unavailable"}
    if (state.budget.tool_calls_used >= state.budget.max_tool_calls or state.budget.deadline and
            datetime.now(timezone.utc) >= state.budget.deadline):
        return {"status":"unavailable", "reason":"report_source_budget_exhausted"}
    started = monotonic()
    state.budget.tool_calls_used += 1
    seq = state.budget.tool_calls_used
    result = error = None
    try:
        result = call_tool(registry, "read_pdf_cell", args, state.budget.deadline)
    except ToolError as exc:
        error = exc.code
    state.actions.append(ActionRecord(seq=seq, tool="read_pdf_cell", tool_execution_id=f"{state.run_id}:{seq}",
        input_digest=digest(canonical(args)), output_digest=digest(canonical(result)) if result else None,
        status="error" if error else "done", error_code=error, elapsed_ms=round((monotonic()-started)*1000)))
    if error:
        return {"status":"unavailable", "reason":error}
    return {"status":"source_verified", "source_scope":result["source_scope"],
            "cell":result}
