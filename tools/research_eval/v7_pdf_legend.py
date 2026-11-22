"""Read selected legend zones from an explicitly identified publisher edition."""
import argparse
import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import subprocess
from time import monotonic

from tools.research_eval.inputs import ROOT
from tools.research_eval.v7_pdf import PDF_HASH


# AI visual transcription from the publisher bitmaps. Never used by the recognizer.
LEGENDS = {4: ["OLEM", "OLTM"], 5: ["New", "Split", "Join", "Move", "Keep", "Dense"],
           6: ["New", "Split", "Join", "Move", "Keep", "Dense"]}


def recognize(executable, image, box, psm):
    tile = image.crop(box)
    encoded = BytesIO()
    tile.save(encoded, format="PNG")
    reply = subprocess.run([str(executable), "stdin", "stdout", "-l", "eng", "--psm", str(psm), "tsv"],
                           input=encoded.getvalue(), capture_output=True, check=True, timeout=15)
    words = []
    for entry in csv.DictReader(StringIO(reply.stdout.decode("utf8")), delimiter="\t"):
        if entry["level"] == "5" and entry["text"].strip():
            x, y, w, h = (int(entry[k]) for k in ("left", "top", "width", "height"))
            if not (0 <= x < x+w <= tile.width and 0 <= y < y+h <= tile.height):
                raise ValueError("word outside OCR crop")
            words.append({"text": entry["text"], "confidence": round(float(entry["conf"]), 2),
                          "pixel_bbox": [box[0]+x, box[1]+y, box[0]+x+w, box[1]+y+h]})
    return words


def evaluate(pdf, executable):
    from pypdf import PdfReader

    started = monotonic()
    bindings = json.loads((ROOT / "docs/agent-v7/figure-results.json").read_bytes())
    digest = sha256(pdf.read_bytes()).hexdigest()
    if digest != PDF_HASH or digest != bindings["pdf_sha256"]:
        raise ValueError("unrecognized publisher edition")
    reader = PdfReader(pdf)
    totals = {"expected_labels": 0, "whole_exact": 0, "crop_exact": 0}
    cases = []
    for source in bindings["matched"]:
        number = source["number"]
        if number not in LEGENDS:
            continue
        page = reader.pages[source["page"]-1]
        if len(page.images) != 1:
            raise ValueError("ambiguous source image")
        image = page.images[0].image.convert("RGB")
        if list(image.size) != source["size"] or sha256(image.tobytes()).hexdigest() != source["rgb_sha256"]:
            raise ValueError("publisher raster mismatch")
        w, h = image.size
        box = tuple(round(v*scale) for v, scale in zip((.855, .754, .935, .947), (w, h, w, h)))
        whole = recognize(executable, image, (0, 0, w, h), 11)
        inside = [r for r in whole if box[0] <= r["pixel_bbox"][0] < box[2] and box[1] <= r["pixel_bbox"][1] < box[3]]
        cropped = recognize(executable, image, box, 6)
        expected = LEGENDS[number]
        def score(words):
            return len({r["text"] for r in words} & set(expected))
        totals["expected_labels"] += len(expected)
        totals["whole_exact"] += score(inside)
        totals["crop_exact"] += score(cropped)
        cases.append({"number": number, "page": source["page"], "figure_pdf_bbox": source["bbox"],
                      "rgb_sha256": source["rgb_sha256"], "crop_pixels": box, "expected": expected,
                      "whole_figure_words_in_region": inside, "crop_words": cropped})
    if {c["number"] for c in cases} != set(LEGENDS):
        raise ValueError("required figures are missing")
    version = subprocess.check_output([str(executable), "--version"], timeout=5).decode("utf8").splitlines()[0]
    return dict(scope="preselected legend regions; AI visual reference; word candidates only",
                pdf_sha256=digest, engine=version, totals=totals, figures=cases,
                elapsed_seconds=round(monotonic()-started, 3))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pdf", type=Path)
    cli.add_argument("--tesseract", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    report = evaluate(args.pdf, args.tesseract.resolve(strict=True))
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(report["totals"])
