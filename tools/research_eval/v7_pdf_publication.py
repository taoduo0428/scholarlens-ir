"""Verify a physical cell in a saved research report against its publisher's XML."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

from backend.research.reports import generate_report
from backend.research.schemas import Scope, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolRegistry
from tools.research_eval.v7_pdf import DOI, PDF_HASH, XML_HASH


def evaluate(pdf, xml):
    markup = xml.read_bytes()
    if sha256(pdf.read_bytes()).hexdigest() != PDF_HASH or sha256(markup).hexdigest() != XML_HASH:
        raise ValueError("unexpected source version")
    table = ET.fromstring(markup).find(".//table-wrap[@id='pone-0102799-t001']")
    rows = table.findall(".//tr")
    cells = [["".join(cell.itertext()) for cell in row] for row in rows]
    assert cells[0][1] == "Number of nodes" and cells[1][0] == "ca-CondMat"
    expected = cells[1][1]
    corpus = LocalCorpus([{"paper_id": DOI}], "licensed-pdf-v1")
    corpus.pdf_resolver = lambda authorized: pdf if authorized["paper_id"] == DOI else None
    scope = Scope(paper_ids=[DOI])
    task = TaskInput(goal="Read the selected cell in publisher table one.", scope=scope,
                     pdf_cell=dict(paper_id=DOI, source_version=PDF_HASH, page=6, table_id=1, row=3, column=2))
    registry = ToolRegistry(corpus, owner_id=1, scope=scope, generation=corpus.generation)
    with TemporaryDirectory() as temp:
        store = ResearchStore(temp)
        state = store.create(1, "cell-evaluation", task, corpus.generation)[0]
        report = generate_report(state, store, registry)
        stored = next(a for a in state.artifact_refs if a.startswith("report-"))
        assert json.loads(store.artifact(1, state.run_id, stored)["content"]) == report
    item = report["pdf_cell_evidence"]
    assert item["status"] == "source_verified"
    cell = item["cell"]
    assert cell["quote"] == expected and cell["quote_sha256"] == sha256(expected.encode()).hexdigest()
    assert cell["source_version"] in cell["locator"] and expected in report["markdown"]
    return {"doi": DOI, "status": "PASS", "publisher_table": table.get("id"),
            "row_label": cells[1][0], "column_label": cells[0][1], "cell": cell,
            "jats_sha256": XML_HASH, "tool_calls": report["spending"]["tools"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("xml", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.pdf, args.xml), indent=2))
