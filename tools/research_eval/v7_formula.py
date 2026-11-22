"""Cross-check PDF formula mentions against PDFium glyphs and the publisher's JATS."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import re
from xml.etree import ElementTree

import pypdfium2 as pdfium

from backend.research.pdf_layout import from_path
from tools.research_eval.v7_pdf import DOI, PDF_HASH, XML_HASH


def digest(text):
    return sha256(text.encode("utf8")).hexdigest()


def evaluate(pdf, xml):
    if sha256(pdf.read_bytes()).hexdigest() != PDF_HASH or sha256(xml.read_bytes()).hexdigest() != XML_HASH:
        raise ValueError("licensed source hash mismatch")
    root = ElementTree.parse(xml).getroot()
    section = root.find(".//sec[@id='s3']")
    paragraph = " ".join("".join(section.find("p").itertext()).split())
    references = list(re.finditer(r"(?P<context>(?:temporal|expected) modularity) \(See (?P<quote>Eq\.\((?P<n>\d+)\))\)", paragraph))
    assert [m["n"] for m in references] == ["4", "6"]
    formulas = {f.findtext("label"): f for f in root.findall(".//disp-formula") if f.findtext("label")}
    layout = from_path(pdf, "figure-eval-paper", 8)
    data = layout["formula_evidence"]
    assert [m["number"] for m in data["mentions"]] == [m["n"] for m in references]
    assert data["equations"] == [] and layout["source_version"] == PDF_HASH
    lines = {row["locator"]: row for row in layout["items"]}
    rows = []
    with pdfium.PdfDocument(pdf) as document, closing(document[7]) as page, closing(page.get_textpage()) as independent:
        for ref, mention in zip(references, data["mentions"], strict=True):
            src = mention["source"]
            line = lines[src["locator"]]
            assert line["quote"][src["start"]:src["end"]] == ref["quote"] == src["quote"]
            assert digest(line["quote"]) == src["line_sha256"] and digest(ref["quote"]) == src["quote_sha256"]
            assert src["locator"].startswith(f"pdf:{PDF_HASH}:p8:text:") and src["bbox"] == line["bbox"]
            assert mention["equation_locator"] is None
            with closing(independent.search(ref["quote"])) as search:
                start, length = search.get_next()
                assert search.get_next() is None
            assert independent.get_text_range(start, length) == ref["quote"]
            glyphs = [independent.get_charbox(i) for i in range(start, start + length)]
            height = page.get_height()
            bbox = [min(g[0] for g in glyphs), height - max(g[3] for g in glyphs),
                    max(g[2] for g in glyphs), height - min(g[1] for g in glyphs)]
            left, top, right, bottom = src["bbox"]
            assert left <= bbox[0] < bbox[2] <= right and top <= bbox[1] < bbox[3] <= bottom
            formula = formulas[f"({ref['n']})"]
            assert formula is not None and [child.tag for child in formula] == ["graphic", "label"]
            rows.append({"number": ref["n"], "product_source": src, "product_equation_locator": None,
                         "pdfium_char_range": [start, start + length],
                         "pdfium_glyph_bbox": [round(n, 3) for n in bbox],
                         "jats_context": ref["context"], "jats_paragraph_char_range": list(ref.span("quote")),
                         "jats_formula_id": formula.get("id"),
                         "jats_formula_graphic": formula.find("graphic").get("{http://www.w3.org/1999/xlink}href")})
    display_pages = {}
    for number, target_page in (("4", 4), ("6", 5)):
        target = from_path(pdf, "figure-eval-paper", target_page)
        found = [e for e in target["formula_evidence"]["equations"] if e["number"] == number]
        assert not found
        display_pages[number] = {"page": target_page, "product_expression": None}
    return {"doi": DOI, "pdf_sha256": PDF_HASH, "xml_sha256": XML_HASH, "page": 8,
            "jats_paragraph": "sec[@id='s3']/p[1]", "jats_paragraph_sha256": digest(paragraph),
            "matched_mentions": len(rows), "mentions": rows, "display_equations": display_pages,
            "verified_expression_transcriptions": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("xml", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate(args.pdf, args.xml)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("matched mentions:", result["matched_mentions"])
