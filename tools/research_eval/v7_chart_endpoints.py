"""Compare registered plot endpoints from the layout API reader with publisher Table 2."""

import argparse
import json
from hashlib import sha256
from pathlib import Path
from statistics import mean
from xml.etree import ElementTree

import numpy as np
from PIL import Image

from backend.research.chart_readings import read_pair
from backend.research.chart_registry import lookup
from backend.research.pdf_layout import from_path
from tools.research_eval.inputs import ROOT
from tools.research_eval.v7_pdf import PDF_HASH, XML_HASH


def source_table(source):
    assert sha256(source.read_bytes()).hexdigest() == XML_HASH
    root = ElementTree.parse(source)
    table = root.find(".//table-wrap[@id='pone-0102799-t002']")
    header, *rows = table.findall(".//tr")
    columns = ["".join(cell.itertext()) for cell in header]
    assert columns == ["Data set", "OLEM", "OLTM", "Louvain"]
    result = {}
    for row in rows:
        name, *values = ["".join(cell.itertext()) for cell in row]
        result[name] = {k: float(v) for k, v in zip(columns[1:3], values[:2])}
    assert len(result) == 11
    return result


def evaluate(pdf, xml, publisher_image):
    sources = json.loads((ROOT / "docs/agent-v7/figure-results.json").read_bytes())
    (source,) = [f for f in sources["matched"] if f["number"] == 4]
    assert sha256(pdf.read_bytes()).hexdigest() == sources["pdf_sha256"] == PDF_HASH
    assert (
        sha256(publisher_image.read_bytes()).hexdigest()
        == source["publisher_file_sha256"]
    )
    with Image.open(publisher_image) as asset:
        image = np.array(asset.convert("RGB"))
    result = from_path(pdf, "figure-eval-paper", 6)
    assert result["chart_series"] == "calibrated_endpoints"
    (chart,) = result["chart_readings"]
    _, calibration = lookup(result)
    assert chart["calibration_id"] == calibration.id
    assert (
        chart["rgb_sha256"]
        == sha256(image.tobytes()).hexdigest()
        == source["rgb_sha256"]
    )
    assert chart["caption_quote_sha256"] == source["caption_line_sha256"]
    assert chart["source_version"] == PDF_HASH
    assert chart["x_axis"]["at"] == 100
    reference = source_table(xml)
    assert {p["dataset"] for p in chart["panels"]} == set(reference)
    measured, missing, errors, masked = [], [], [], 0
    for panel in chart["panels"]:
        dataset, frame = panel["dataset"], panel["frame_pixels"]
        points = panel["points"]
        if not points:
            assert panel["status"] == "indistinct_endpoint"
            missing.append(dataset)
            continue
        assert {p["series"] for p in points} == set(reference[dataset])
        for point in points:
            table_value = reference[dataset][point["series"]]
            absolute_error = abs(table_value - point["estimate"])
            assert point["interval"][0] <= table_value <= point["interval"][1]
            assert absolute_error <= 0.015
            errors.append(absolute_error)
            measured.append(
                dict(
                    dataset=dataset,
                    **point,
                    table_value=table_value,
                    absolute_error=round(absolute_error, 5),
                )
            )

        # Remove only the final sample column from a publisher copy, keeping
        # the axis calibration and earlier colored samples available.
        _, top, right, bottom = frame
        cropped = image[top : bottom + 1, right - 2 : right + 1].copy()
        try:
            image[top : bottom + 1, right] = 255
            assert read_pair(image, frame, calibration.colors(), -0.5, 1) == []
        finally:
            image[top : bottom + 1, right - 2 : right + 1] = cropped
        masked += 1
    assert len(measured) == 8 and len(missing) == 7
    return {
        "doi": sources["doi"],
        "page": 6,
        "figure": 4,
        "paper_id": chart["paper_id"],
        "pdf_sha256": PDF_HASH,
        "xml_sha256": XML_HASH,
        "rgb_sha256": chart["rgb_sha256"],
        "calibration": "image-registered linear axes, panel labels and two legend colors",
        "reference": "publisher JATS table pone-0102799-t002, columns OLEM and OLTM",
        "axes": {"x": chart["x_axis"], "y": chart["y_axis"]},
        "reference_values": 22,
        "reported": len(measured),
        "inside_reported_interval": len(errors),
        "max_absolute_error": round(max(errors), 5),
        "mean_absolute_error": round(mean(errors), 5),
        "panels_withheld": missing,
        "masked_panels_abstained": masked,
        "points": measured,
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for parameter in ("pdf", "xml", "publisher_image"):
        cli.add_argument(parameter, type=Path)
    cli.add_argument("--output", required=True, type=Path)
    args = cli.parse_args()
    report = evaluate(args.pdf, args.xml, args.publisher_image)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print("reported", report["reported"], "max error", report["max_absolute_error"])
