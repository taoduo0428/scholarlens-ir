"""Publication checks through the real tool registry and the saved report."""
from hashlib import sha256

import pytest
from pydantic import ValidationError

from backend.research.reports import generate_report
from backend.research.schemas import Scope, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolRegistry
from backend.tests.research.test_pdf_layout import specimen


def setup_task(tmp_path, *, owner=7, version=None, row=2, limited=False):
    raw = specimen()
    path = tmp_path / "fixture.pdf"
    path.write_bytes(raw)
    # Privacy follows the authoritative document, even for a legacy opaque ID.
    doc = {"paper_id": "table-paper", "owner_id": 7}
    corpus = LocalCorpus([doc], "test-generation")
    corpus.pdf_resolver = lambda authorized: path
    scope = Scope(paper_ids=["table-paper"], include_own_uploads=True)
    request = dict(paper_id="table-paper", page=1, table_id=1, row=row, column=2,
                   source_version=version or sha256(raw).hexdigest())
    task = TaskInput(goal="Read one cell", scope=scope, pdf_cell=request)
    store = ResearchStore(tmp_path)
    state = store.create(owner, "cell", task, corpus.generation)[0]
    if limited:
        state.budget.tool_calls_used = state.budget.max_tool_calls
    registry = ToolRegistry(corpus, owner_id=owner, scope=scope, generation=corpus.generation)
    return state, store, registry


def test_publishes_scoped_cell_and_charges_read(tmp_path):
    pytest.importorskip("pdfplumber")
    state, store, registry = setup_task(tmp_path)
    report = generate_report(state, store, registry)
    result = report["pdf_cell_evidence"]
    assert (result["status"], result["source_scope"]) == ("source_verified", "owner_only")
    cell = result["cell"]
    assert cell["quote"] == "87" and cell["quote_sha256"] == sha256(b"87").hexdigest()
    assert cell["bbox"] == [110.0, 140.0, 210.0, 180.0]
    assert f"pdf:{state.task.pdf_cell.source_version}:p1:cell:" in cell["locator"]
    assert "87" in report["markdown"] and report["spending"]["tools"] == 1
    assert [(a.tool, a.status) for a in state.actions] == [("read_pdf_cell", "done")]
    assert not report["claims"]


@pytest.mark.parametrize(("options", "reason", "charge"), [
    ({"owner": 8}, "paper_not_found", 1),
    ({"version": "0" * 64}, "layout_version_mismatch", 1),
    ({"row": 99}, "cell_not_found", 1),
    ({"limited": True}, "report_source_budget_exhausted", 0),
])
def test_unavailable_cell_is_not_published(tmp_path, options, reason, charge):
    pytest.importorskip("pdfplumber")
    state, store, registry = setup_task(tmp_path, **options)
    if reason == "paper_not_found":
        registry.corpus.pdf_resolver = lambda doc: pytest.fail("opened a foreign file")
    before = state.budget.tool_calls_used
    report = generate_report(state, store, registry)
    assert report["pdf_cell_evidence"] == {"status": "unavailable", "reason": reason}
    assert state.budget.tool_calls_used - before == charge
    assert not report["claims"]


def test_unscoped_request_is_rejected(tmp_path):
    state, _, _ = setup_task(tmp_path)
    with pytest.raises(ValidationError, match="explicitly scoped"):
        TaskInput(goal="Read a cell", pdf_cell=state.task.pdf_cell)
