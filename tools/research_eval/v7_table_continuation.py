"""Compare a continued physical PDF table with the publisher's full JATS grid."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from xml.etree import ElementTree as ET

from backend.research.pdf_layout import page_evidence
from tools.research_eval.v7_pdf import normalized

DOI = "10.1371/journal.pone.0081798"
PDF_HASH = "ca2073de944a8ef60f5e12a9910cbba951e39785b9521c9ef130f743aa959f5c"
XML_HASH = "bfd7fb0af1cf91110648e0c2f90fd52fc79e9512630abf9fe8e93ad398df0ae7"


def publisher_row(row):
    """Map the two subcolumns of the JATS characteristic column onto the PDF label."""
    cells = [(int(c.get("colspan", 1)), normalized("".join(c.itertext()))) for c in row]
    if [w for w, _ in cells] == [2, 1, 1, 1]:
        return [v for _, v in cells]
    if len(cells) == 5 and all(w == 1 for w, _ in cells) and cells[0][1] == "":
        return [v for _, v in cells[1:]]
    if len(cells) == 1 and cells[0][0] == 5:
        return [cells[0][1], "", "", ""]
    raise ValueError("unexpected JATS column geometry")


def evaluate(pdf, xml):
    from pypdf import PdfReader

    start = monotonic()
    raw, markup = pdf.read_bytes(), xml.read_bytes()
    if (sha256(raw).hexdigest(), sha256(markup).hexdigest()) != (PDF_HASH, XML_HASH):
        raise ValueError("publisher edition mismatch")
    root = ET.fromstring(markup)
    reference = root.find(".//table-wrap[@id='pone-0081798-t001']")
    expected = [publisher_row(r) for r in reference.findall(".//tr")]
    pages = len(PdfReader(pdf).pages)
    layouts = [page_evidence(raw, DOI, p) for p in range(1, pages + 1)]
    links = [link for layout in layouts for link in layout["table_continuations"]]
    if len(links) != 1 or links[0]["number"] != 1:
        raise ValueError("ambiguous or missing continuation")
    link = links[0]
    data, physical = [], []
    for key, page in (("previous", 3), ("current", 4)):
        info = link[key]
        if info["page"] != page:
            raise ValueError("wrong source page")
        items = layouts[page - 1]["items"]
        by_locator = {i["locator"]: i for i in items}
        table = by_locator[info["table_locator"]]
        if by_locator[info["caption_locator"]]["quote_sha256"] != info["caption_quote_sha256"]:
            raise ValueError("caption binding mismatch")
        grid = {}
        for c in items:
            if c["kind"] != "cell" or c["table_id"] != table["table_id"]:
                continue
            if sha256(c["quote"].encode()).hexdigest() != c["quote_sha256"]:
                raise ValueError("cell hash does not match")
            grid.setdefault(c["row"], {})[c["column"]] = normalized(c["quote"])
        rows = [[values.get(column, "") for column in range(1, 5)] for _, values in sorted(grid.items())]
        if rows[0] != expected[0]:
            raise ValueError("header or unit mismatch")
        data.extend(rows if key == "previous" else rows[1:])
        physical.append({"page": page, "rows": len(rows), "physical_cells": sum(map(len, grid.values()))})
    if data != expected:
        raise ValueError("logical table differs from publisher reference")
    return dict(doi=DOI, pdf_sha256=PDF_HASH, xml_sha256=XML_HASH, pages=pages, link=link,
                physical=physical, logical_rows=len(expected), logical_columns=4,
                nonempty_values=sum(bool(v) for row in expected for v in row),
                status="PASS", elapsed_seconds=round(monotonic() - start, 3))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pdf", type=Path)
    cli.add_argument("xml", type=Path)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    report = evaluate(args.pdf, args.xml)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(report["status"], report["logical_rows"], report["nonempty_values"])
