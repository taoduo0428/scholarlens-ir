"""Verify the installed OCR engine through the product's colour legend reader."""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from backend.research.figure_legend import labels, swatch_stack


def main():
    engine = Path(os.environ["SCHOLARLENS_TESSERACT"])
    image = Image.new("RGB", (480, 180), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=28)
    reference = [("River", "#ff0000"), ("Lake", "#0000ff"), ("Forest", "#008000")]
    for idx, (word, color) in enumerate(reference):
        y = 20 + idx * 42
        draw.rectangle((20, y, 77, y + 27), fill=color)
        draw.text((84, y + 14), word, fill="black", anchor="lm", font=font)
    readings = labels(image, swatch_stack(image), engine)
    if [(entry["text"], entry["color"]) for entry in readings] != reference:
        raise RuntimeError("ocr_legend_smoke_failed")
    print("3 synthetic labels and their swatch colors verified")


if __name__ == "__main__":
    main()
