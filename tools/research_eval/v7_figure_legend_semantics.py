"""Verify full-page legend recovery against publisher images and a dated visual reference."""

import argparse
import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path
from time import monotonic

from PIL import Image

from backend.research.figure_legend import labels, swatch_stack
from backend.research.pdf_layout import from_path
from tools.research_eval.inputs import ROOT
from tools.research_eval.v7_pdf import PDF_HASH


def transformed_controls(image, entries, executable):
    """Remove only text, then relocate the entire publisher key on a same-size canvas."""
    original = swatch_stack(image)
    assert len(original) == len(entries)
    masked = image.copy()
    for entry in entries:
        masked.paste("white", tuple(entry["label_pixels"]))
    masked_stack = swatch_stack(masked)
    assert masked_stack == original
    assert labels(masked, masked_stack, executable) == []

    boxes = [
        entry[key] for entry in entries for key in ("swatch_pixels", "label_pixels")
    ]
    left = min(box[0] for box in boxes) - 8
    top = min(box[1] for box in boxes) - 8
    right = max(box[2] for box in boxes) + 8
    bottom = max(box[3] for box in boxes) + 8
    canvas = Image.new("RGB", image.size, "white")
    destination = (120, 140)
    canvas.paste(image.crop((left, top, right, bottom)), destination)
    delta = (destination[0] - left, destination[1] - top)
    moved = labels(canvas, swatch_stack(canvas), executable)
    assert [e["text"] for e in moved] == [e["text"] for e in entries]
    errors = []
    for old, new in zip(entries, moved):
        assert old["color"] == new["color"]
        errors.extend(
            abs(b - a - delta[i % 2])
            for key in ("label_pixels", "swatch_pixels")
            for i, (a, b) in enumerate(zip(old[key], new[key]))
        )
    assert max(errors) <= 3
    return {
        "text_masked": {"swatches_remaining": len(masked_stack), "labels": 0},
        "translated": {
            "delta": delta,
            "labels": len(moved),
            "max_pixel_error": max(errors),
        },
    }


def verify_entry(entry, source, image, reference):
    text = entry["text"]
    assert entry["text_sha256"] == sha256(text.encode()).hexdigest()
    (known,) = [r for r in reference["crop_words"] if r["text"] == text]
    assert entry["label_pixels"] == known["pixel_bbox"]
    x0, y0, x1, y1 = entry["swatch_pixels"]
    sampled = "#{:02x}{:02x}{:02x}".format(
        *image.getpixel(((x0 + x1) // 2, (y0 + y1) // 2))
    )
    assert entry["color"] == sampled
    origin_x, origin_y, right, bottom = source["bbox"]
    scale = ((right - origin_x) / image.width, (bottom - origin_y) / image.height)
    for kind in ("swatch", "label"):
        box = entry[kind + "_pixels"]
        assert (
            0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height
        )
        projected = [
            round((origin_x, origin_y)[i % 2] + v * scale[i % 2], 3)
            for i, v in enumerate(box)
        ]
        assert projected == entry[kind + "_pdf_bbox"]


def evaluate(pdf, publisher_dir, executable):
    started = monotonic()
    refs = ROOT / "docs/agent-v7"
    bindings = json.loads((refs / "figure-results.json").read_bytes())
    ocr = json.loads((refs / "legend-ocr-results.json").read_bytes())
    assert (
        sha256(pdf.read_bytes()).hexdigest()
        == bindings["pdf_sha256"]
        == ocr["pdf_sha256"]
        == PDF_HASH
    )
    by_number = {row["number"]: row for row in ocr["figures"]}
    assert set(by_number) == {4, 5, 6}
    assert [s["number"] for s in bindings["matched"]] == [1, 2, 3, 4, 5, 6]
    doi = bindings["doi"]
    totals = {
        "visual_reference_labels": 0,
        "matched": 0,
        "missing": 0,
        "extra_in_reference_figures": 0,
    }
    cases = []
    for source in bindings["matched"]:
        number, page = source["number"], source["page"]
        publisher = publisher_dir / f"publisher-g{number:03}.img"
        assert (
            sha256(publisher.read_bytes()).hexdigest()
            == source["publisher_file_sha256"]
        )
        with Image.open(publisher) as asset:
            image = asset.convert("RGB")
        assert sha256(image.tobytes()).hexdigest() == source["rgb_sha256"]
        layout = from_path(pdf, doi, page)
        assert (
            layout["source_version"] == PDF_HASH
            and layout["paper_id"] == doi
            and layout["page"] == page
        )
        (link,) = [
            link for link in layout["figure_caption_links"] if link["number"] == number
        ]
        (caption,) = [
            i for i in layout["items"] if i["locator"] == link["caption_locator"]
        ]
        (region,) = [
            i for i in layout["items"] if i["locator"] == link["figure_locator"]
        ]
        assert (
            source["caption_line_sha256"]
            == caption["quote_sha256"]
            == link["caption_quote_sha256"]
        )
        assert (
            caption["bbox"] == source["caption_bbox"]
            and region["bbox"] == source["bbox"]
        )
        legends = layout["figure_legends"]
        entries = []
        case = {
            "number": number,
            "page": page,
            "rgb_sha256": source["rgb_sha256"],
            "caption_sha256": link["caption_quote_sha256"],
            "entries": entries,
        }
        reference = by_number.get(number)
        if number in (5, 6):
            (legend,) = legends
            assert all(legend[k] == v for k, v in link.items())
            assert (legend["page"], legend["paper_id"], legend["source_version"]) == (
                page,
                doi,
                PDF_HASH,
            )
            assert legend["rgb_sha256"] == source["rgb_sha256"] and legend[
                "image_size"
            ] == list(image.size)
            entries.extend(legend["entries"])
            assert [e["text"] for e in entries] == reference["expected"]
            for entry in entries:
                verify_entry(entry, source, image, reference)
            case["transformed_controls"] = transformed_controls(
                image, entries, executable
            )
        else:
            assert legends == []
        if reference is not None:
            assert (reference["page"], reference["rgb_sha256"]) == (
                page,
                source["rgb_sha256"],
            )
            known, found = set(reference["expected"]), {e["text"] for e in entries}
            totals["visual_reference_labels"] += len(known)
            totals["matched"] += len(known & found)
            totals["missing"] += len(known - found)
            totals["extra_in_reference_figures"] += len(found - known)
            case["missing_labels"] = sorted(known - found)
        cases.append(case)
    version = (
        subprocess.check_output([str(executable), "--version"], timeout=5)
        .decode()
        .splitlines()[0]
    )
    return {
        "doi": doi,
        "pdf_sha256": PDF_HASH,
        "engine": version,
        "language": "eng",
        "entry_point": "backend.research.pdf_layout.from_path",
        "publisher_figures": len(cases),
        "reference": "AI visual transcription of three figures plus previous OCR word boxes",
        "totals": totals,
        "figures": cases,
        "elapsed_seconds": round(monotonic() - started, 3),
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pdf", type=Path)
    cli.add_argument("publisher_dir", type=Path)
    cli.add_argument("--tesseract", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    executable = args.tesseract.resolve(strict=True)
    os.environ["SCHOLARLENS_TESSERACT"] = str(executable)
    report = evaluate(args.pdf, args.publisher_dir, executable)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(report["totals"])
