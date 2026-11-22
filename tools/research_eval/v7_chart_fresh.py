"""Register a new two-trace laboratory figure and read its known endpoints through PDF layout."""

import argparse
import json
import os
import tempfile
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from backend.research.pdf_layout import from_path


def sample():
    """Render known values against explicitly drawn linear axes in a new PDF."""
    image = Image.new("RGB", (200, 145), "white")
    drawing = ImageDraw.Draw(image)
    frame = [27, 18, 161, 118]
    drawing.rectangle(frame, outline="black")
    drawing.text((2, 12), "80", fill="black")
    drawing.text((0, 109), "-20", fill="black")
    drawing.text((20, 121), "-5", fill="black")
    drawing.text((155, 121), "25", fill="black")
    drawing.text((68, 127), "Time (s)", fill="black")
    known = {"Canal": 56, "Pool": -1}
    colors = {"Canal": "#74159f", "Pool": "#ad751b"}
    for index, (name, endpoint) in enumerate(known.items()):
        # The declared scale is 100 units across 100 pixel centers.
        final_y = frame[1] + 80 - endpoint
        drawing.line(
            [(27, 64 + 30 * index), (92, final_y + 11), (145, final_y), (161, final_y)],
            fill=colors[name],
            width=5,
        )
        drawing.text((115 * index + 5, 1), name, fill=colors[name])

    writer = PdfWriter()
    page = writer.add_blank_page(240, 195)
    picture = DecodedStreamObject()
    picture.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
            NameObject("/Width"): NumberObject(image.width),
            NameObject("/Height"): NumberObject(image.height),
        }
    )
    picture.set_data(image.tobytes())
    caption = "Figure 7. Fresh two-trace calibration."
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject("/Plot"): writer._add_object(picture)}
            ),
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        }
    )
    commands = DecodedStreamObject()
    commands.set_data(
        f"q 200 0 0 145 15 35 cm /Plot Do Q\nBT /F1 10 Tf 15 22 Td ({caption}) Tj ET".encode()
    )
    page[NameObject("/Contents")] = writer._add_object(commands)
    output = BytesIO()
    writer.write(output)
    raw = output.getvalue()
    profile = {
        "id": "fresh-pool-v1",
        "source_version": sha256(raw).hexdigest(),
        "rgb_sha256": sha256(image.tobytes()).hexdigest(),
        "caption_sha256": sha256(caption.encode()).hexdigest(),
        "page": 1,
        "figure": 7,
        "size": list(image.size),
        "x_axis": {"label": "Time (s)", "min": -5, "max": 25},
        "y_axis": {"label": "Temperature (C)", "min": -20, "max": 80},
        "panels": {"Laboratory": frame},
        "series": colors,
    }
    return raw, profile, known


def evaluate(folder):
    raw, profile, known = sample()
    pdf = folder / "fresh.pdf"
    pdf.write_bytes(raw)
    registry = folder / "custom.json"
    registry.write_text(json.dumps({"version": 1, "profiles": []}), encoding="utf8")
    with patch.dict(
        os.environ,
        {"SCHOLARLENS_CHART_CALIBRATIONS": str(registry), "SCHOLARLENS_TESSERACT": ""},
    ):
        first = from_path(pdf, "fresh-calibration", 1)
        assert (
            first["chart_reading_status"] == "unregistered"
            and first["chart_readings"] == []
        )
        registry.write_text(
            json.dumps({"version": 1, "profiles": [profile]}), encoding="utf8"
        )
        result = from_path(pdf, "fresh-calibration", 1)
        (chart,) = result["chart_readings"]
        (panel,) = chart["panels"]
        measured = {p["series"]: p["estimate"] for p in panel["points"]}
        assert (
            measured == known
            and chart["x_axis"]["at"] == 25
            and chart["calibration_id"] == profile["id"]
        )
        assert all(
            point["interval"][0] <= known[point["series"]] <= point["interval"][1]
            for point in panel["points"]
        )
        registry.write_text("{}", encoding="utf8")
        invalid = from_path(pdf, "fresh-calibration", 1)
        assert (
            invalid["chart_reading_status"] == "registry_unavailable"
            and invalid["chart_readings"] == []
        )
        registry.write_text(
            json.dumps(
                {"version": 1, "profiles": [dict(profile, rgb_sha256="0" * 64)]}
            ),
            encoding="utf8",
        )
        mismatch = from_path(pdf, "fresh-calibration", 1)
        assert (
            mismatch["chart_reading_status"] == "raster_unavailable_or_mismatch"
            and mismatch["chart_readings"] == []
        )
    return {
        "sample": "fresh generated test chart",
        "axes": {"x": chart["x_axis"], "y": chart["y_axis"]},
        "calibration": profile["id"],
        "pdf_sha256": profile["source_version"],
        "rgb_sha256": profile["rgb_sha256"],
        "known_values": known,
        "measured": panel["points"],
        "empty_registry": first["chart_reading_status"],
        "invalid_registry": invalid["chart_reading_status"],
        "wrong_pixels": mismatch["chart_reading_status"],
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", required=True, type=Path)
    args = cli.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        report = evaluate(Path(folder))
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(report["known_values"])
