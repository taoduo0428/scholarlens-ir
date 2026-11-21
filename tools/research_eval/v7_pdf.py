"""Cross-check PDF cell locations against the publisher's JATS tables for a licensed paper."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import time
import unicodedata
import xml.etree.ElementTree as ET

from backend.research.pdf_layout import page_evidence


DOI = "10.1371/journal.pone.0102799"
PDF_HASH = "da9bc35ff925feb8c278c20f06604c3c10eba13afa075476b210e6902da0affa"
XML_HASH = "dacebe67fcabd7057895bd587a96c5ebbcc272163a1a4bd61879ddd0583ef49d"


def normalized(text):
    return "".join(unicodedata.normalize("NFC", text).split())


def evaluate(pdf, xml):
    import pdfplumber

    started = time.monotonic()
    raw = pdf.read_bytes()
    markup = xml.read_bytes()
    if sha256(raw).hexdigest() != PDF_HASH or sha256(markup).hexdigest() != XML_HASH:
        raise ValueError("publisher input hash mismatch")
    root = ET.fromstring(markup)
    tables = {}
    for table in root.findall(".//table-wrap"):
        grid = [
            tuple(normalized("".join(cell.itertext())) for cell in row if cell.tag in {"td", "th"})
            for row in table.findall(".//tr")
        ]
        tables[table.get("id")] = grid

    with pdfplumber.open(pdf) as doc:
        pages = len(doc.pages)
    kinds = Counter()
    matches, unmatched, seen = [], [], set()
    for page in range(1, pages + 1):
        result = page_evidence(raw, DOI, page)
        candidates = defaultdict(lambda: defaultdict(dict))
        for item in result["items"]:
            x0, y0, x1, y1 = item["bbox"]
            assert 0 <= x0 < x1 <= result["width"] and 0 <= y0 < y1 <= result["height"]
            assert item["locator"].startswith(f"pdf:{PDF_HASH}:p{page}:{item['kind']}:")
            assert sha256(item["quote"].encode()).hexdigest() == item["quote_sha256"]
            kinds[item["kind"]] += 1
            if item["kind"] == "cell":
                candidates[item["table_id"]][item["row"]][item["column"]] = normalized(item["quote"])
        for candidate, rows in candidates.items():
            grid = [tuple(row.get(c, "") for c in range(1, max(row) + 1))
                    for _, row in sorted(rows.items()) if any(row.values())]
            # Preserve row order, column positions and punctuation. Ignore blank separator rows.
            exact = [key for key, reference in tables.items() if reference == grid and key not in seen]
            record = {"page": page, "pdf_table_id": candidate}
            if len(exact) == 1:
                seen.add(exact[0])
                matches.append(dict(record, jats_id=exact[0], cells=sum(map(len, grid))))
            else:
                unmatched.append(record)
    return dict(doi=DOI, license="CC BY 4.0", pdf_sha256=PDF_HASH, jats_sha256=XML_HASH,
                pages=pages, jats_tables=len(tables), jats_figures=len(root.findall(".//fig")),
                kinds=dict(kinds), exact_tables=matches, unmatched_candidates=unmatched,
                unmatched_references=sorted(set(tables) - seen), elapsed_seconds=round(time.monotonic()-started, 3))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("jats", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.pdf, args.jats)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print("pages", result["pages"], "exact publisher tables", len(result["exact_tables"]), "/", result["jats_tables"])
