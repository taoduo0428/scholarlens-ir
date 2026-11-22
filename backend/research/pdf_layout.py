"""Read a bounded PDF page from an already authorized document. Coordinates are PDF points."""
from hashlib import sha256
import io
import math
import re

MAX_BYTES = 16 * 1024 * 1024


def figure_caption_links(items):
    """Pair a stand-alone image with its uniquely adjacent numbered caption line."""
    figures = [item for item in items if item["kind"] == "figure"]
    pairs = []
    seen_labels = {}
    for caption in (item for item in items if item["kind"] == "caption"):
        label = re.match(r"^(?:figure|fig\.|图)\s*([1-9]\d{0,3})\s*[.:：．、]", caption["quote"], re.I)
        if not label:
            continue
        number = int(label[1])
        seen_labels[number] = seen_labels.get(number, 0) + 1
        left, top, right, _ = caption["bbox"]
        for figure in figures:
            x0, _, x1, bottom = figure["bbox"]
            overlap = min(right, x1) - max(left, x0)
            if 0 <= top - bottom <= 24 and overlap >= 0.65 * min(right - left, x1 - x0):
                pairs.append((number, figure["locator"], caption["locator"], caption["quote_sha256"]))
    from collections import Counter
    image_counts = Counter(image for _, image, _, _ in pairs)
    caption_counts = Counter(line for _, _, line, _ in pairs)
    return [{"number": number, "figure_locator": image, "caption_locator": line,
             "caption_quote_sha256": digest, "basis": "unique_adjacent_caption"}
            for number, image, line, digest in pairs
            if seen_labels[number] == image_counts[image] == caption_counts[line] == 1]


def _single_page(pdf_bytes: bytes, paper_id: str, page_number: int, version: str):
    """Extract physical regions. Unlabelled numerical series cannot become measurements."""
    import pdfplumber
    from backend.research.banded_tables import banded_tables

    items = []

    def add(kind, box, quote="", **attrs):
        bbox = tuple(round(float(x), 3) for x in box)
        if (len(items) >= 1200 or not all(math.isfinite(x) for x in bbox)
                or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]):
            return
        content = quote[:1500]
        locator = f"pdf:{version}:p{page_number}:{kind}:" + ",".join(map(str, bbox))
        items.append(dict(kind=kind, locator=locator, bbox=bbox, quote=content,
                          quote_sha256=sha256(content.encode()).hexdigest(), **attrs))

    with pdfplumber.open(io.BytesIO(pdf_bytes), pages=[page_number]) as doc:
        if not doc.pages:
            raise ValueError("page_out_of_range")
        page = doc.pages[0]
        lines = page.extract_text_lines(return_chars=False)[:600]
        captions = [{"bbox": (ln["x0"], ln["top"], ln["x1"], ln["bottom"])} for ln in lines
                    if re.match(r"^(?:table|表)\s*\d+", ln["text"], re.I)]
        ruled = page.find_tables()[:20]
        tables = ruled + (banded_tables(page, captions, ruled) if len(ruled) < 20 else [])
        for idx, table in enumerate(tables, 1):
            add("table", table.bbox, table_id=idx)
            values = table.extract()
            for row, record in enumerate(table.rows[:100]):
                for col, cell in enumerate(record.cells[:40]):
                    if cell:
                        add("cell", cell, values[row][col] or "", table_id=idx, row=row + 1, column=col + 1,
                            header_candidate=(values[0][col] or "")[:120])
        for entry in page.images[:100]:
            add("figure", (entry["x0"], entry["top"], entry["x1"], entry["bottom"]),
                interpretation="region_only")
        for line in lines:
            text = line["text"]
            kind = ("caption" if re.match(r"^(?:figure|fig\.|table|图|表)\s*\d+", text, re.I)
                    else "formula" if re.search(r"=\s*[^=].{0,130}\(\d+[a-z]?\)\s*$", text)
                    else "reference" if re.match(r"^\[\d+\]\s+\S", text)
                    else "text")
            add(kind, (line["x0"], line["top"], line["x1"], line["bottom"]), text)
        return {"paper_id": paper_id, "page": page.page_number, "source_version": version,
                "width": float(page.width), "height": float(page.height), "coordinate_system": "pt_top_left",
                "items": items, "figure_caption_links": figure_caption_links(items), "ocr": "unavailable", "cross_page_table_links": "unverified",
                "chart_series": "unverified", "engine": "pdfplumber/" + pdfplumber.__version__}


def page_evidence(pdf_bytes: bytes, paper_id: str, page_number: int):
    """Read physical source regions and resolve explicit continuations in this edition."""
    from backend.research.table_continuation import continuation_number, link_tables
    from backend.research.figure_legend import page_legends

    if not 1 <= page_number <= 500 or len(pdf_bytes) > MAX_BYTES or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("invalid_document_or_page")
    version = sha256(pdf_bytes).hexdigest()
    current = _single_page(pdf_bytes, paper_id, page_number, version)
    current["figure_legends"] = page_legends(pdf_bytes, current)
    if current["figure_legends"]:
        current["ocr"] = "figure_legend_labels"
    current["table_continuations"] = []
    if page_number > 1 and any(continuation_number(i) for i in current["items"]):
        previous = _single_page(pdf_bytes, paper_id, page_number - 1, version)
        current["table_continuations"] = link_tables(previous, current)
        if current["table_continuations"]:
            current["cross_page_table_links"] = "source_matched"
    return current


def from_path(path, paper_id, page):
    """Parse in a short-lived process to enforce a deadline on document decoding."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("document_too_large")
    result = subprocess.run([sys.executable, "-m", "backend.research.pdf_layout", paper_id, str(page)],
                            input=raw, capture_output=True, timeout=12, check=False,
                            cwd=Path(__file__).resolve().parents[2])
    if result.returncode == 3:
        raise RuntimeError("layout_dependency_unavailable")
    if result.returncode or len(result.stdout) > 4_000_000:
        raise ValueError("layout_unavailable")
    return json.loads(result.stdout)


if __name__ == "__main__":
    import json
    import sys

    try:
        extracted = page_evidence(sys.stdin.buffer.read(MAX_BYTES + 1), sys.argv[1], int(sys.argv[2]))
        sys.stdout.buffer.write(json.dumps(extracted, ensure_ascii=False).encode("utf8"))
    except ImportError:
        sys.exit(3)
    except Exception:
        sys.exit(2)
