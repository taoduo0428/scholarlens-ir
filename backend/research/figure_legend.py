"""Recover vertically stacked solid colour keys and adjacent OCR labels."""

import csv
from hashlib import sha256
from io import BytesIO, StringIO
import os
from pathlib import Path
import re
import subprocess


def swatch_stack(image):
    """Find one stack of isolated filled rectangles with uniform geometry."""
    import numpy as np
    from PIL import Image

    scale = min(1, 850 / max(image.size))
    sample = image.resize(
        tuple(max(1, round(k * scale)) for k in image.size), Image.Resampling.NEAREST
    )
    pixels = np.asarray(sample)
    height_px, width_px = pixels.shape[:2]
    white = pixels.min(axis=2) >= 225
    rgb = pixels.astype("int32")
    colored = rgb.max(axis=2) - rgb.min(axis=2) >= 55
    codes = rgb[:, :, 0] * 65536 + rgb[:, :, 1] * 256 + rgb[:, :, 2]
    codes[~colored] = -1
    rects = []
    active = {}
    for y in range(height_px + 1):
        present = set()
        if y < height_px:
            line = codes[y]
            changes = np.flatnonzero(line[1:] != line[:-1]) + 1
            bounds = [0, *changes, width_px]
            for left, right in zip(bounds, bounds[1:]):
                if (
                    5 <= right - left <= 0.20 * width_px
                    and left
                    and right < width_px
                    and line[left] >= 0
                    and white[y, left - 1]
                    and white[y, right]
                ):
                    present.add((int(left), int(right), int(line[left])))
        for key in active.keys() - present:
            left, right, color = key
            top = active.pop(key)
            if (
                3 <= y - top <= min(50, (right - left) / 1.3)
                and (right - left) / (y - top) <= 12
                and top > 0
                and y < height_px
                and white[top - 1, left:right].mean() >= 0.85
                and white[y, left:right].mean() >= 0.85
            ):
                rects.append((left, top, right, y, color))
                if len(rects) > 160:
                    return []
        for key in present:
            active.setdefault(key, y)
    stacks = set()
    for left, top, right, bottom, color in rects:
        height = bottom - top
        rows = sorted(
            (
                a
                for a in rects
                if abs(a[0] - left) <= 2
                and abs(a[2] - right) <= 2
                and abs((a[3] - a[1]) - height) <= max(1, height * 0.23)
            ),
            key=lambda a: a[1],
        )
        if 3 <= len(rows) <= 12 and len({a[4] for a in rows}) == len(rows):
            gaps = [next_row[1] - row[3] for row, next_row in zip(rows, rows[1:])]
            if (
                min(gaps) >= 1
                and max(gaps) <= max(4, height)
                and max(gaps) - min(gaps) <= max(2, height * 0.35)
            ):
                stacks.add(tuple(rows))
    if len(stacks) != 1:
        return []
    return [
        (
            round(left * image.width / width_px),
            round(top * image.height / height_px),
            round(right * image.width / width_px),
            round(bottom * image.height / height_px),
            f"#{color:06x}",
        )
        for left, top, right, bottom, color in stacks.pop()
    ]


def labels(image, stack, exe):
    """Read one label per swatch. Ambiguous text invalidates the entire stack."""
    if not stack:
        return []
    import numpy as np
    from PIL import ImageOps

    h = stack[0][3] - stack[0][1]
    left = max(s[2] for s in stack) + 1
    top, bottom = max(0, stack[0][1] - h // 2), min(image.height, stack[-1][3] + h // 2)
    right = min(image.width, left + min(450, 12 * h))
    if right <= left + 4:
        return []
    tile = image.crop((left, top, right, bottom))
    ink = np.asarray(tile)
    if ((ink.max(axis=2) - ink.min(axis=2)) > 55).mean() > 0.005:
        return []
    pad = 12
    data = BytesIO()
    ImageOps.expand(tile, border=pad, fill="white").save(data, format="PNG")
    result = subprocess.run(
        [str(exe), "stdin", "stdout", "-l", "eng", "--psm", "6", "tsv"],
        input=data.getvalue(),
        capture_output=True,
        check=True,
        timeout=2.5,
    )
    rows = [[] for _ in stack]
    for item in csv.DictReader(StringIO(result.stdout.decode("utf8")), delimiter="\t"):
        if item["level"] != "5" or not item["text"].strip():
            continue
        x, y, width, height = [int(item[k]) for k in ("left", "top", "width", "height")]
        x += left - pad
        y += top - pad
        center = y + height / 2
        matches = [idx for idx, s in enumerate(stack) if s[1] - 1 <= center <= s[3] + 1]
        if (
            len(matches) != 1
            or float(item["conf"]) < 70
            or not 0 < width
            or not 0 < height <= 1.55 * h
            or not left <= x < x + width <= right
            or not top <= y < y + height <= bottom
        ):
            return []
        rows[matches[0]].append(
            (x, y, x + width, y + height, item["text"].strip(), float(item["conf"]))
        )
    output = []
    for swatch, words in zip(stack, rows):
        words.sort()
        if (
            not 1 <= len(words) <= 6
            or words[0][0] - left > h
            or any(b[0] - a[2] > h * 0.75 for a, b in zip(words, words[1:]))
        ):
            return []
        phrase = " ".join(word[4] for word in words)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 +()./%_-]{0,59}", phrase):
            return []
        output.append(
            {
                "text": phrase,
                "color": swatch[4],
                "swatch_pixels": list(swatch[:4]),
                "label_pixels": [
                    min(v[0] for v in words),
                    min(v[1] for v in words),
                    max(v[2] for v in words),
                    max(v[3] for v in words),
                ],
                "confidence": round(min(v[5] for v in words), 2),
                "text_sha256": sha256(phrase.encode()).hexdigest(),
            }
        )
    return output if len({e["text"].casefold() for e in output}) == len(output) else []


def page_legends(pdf_bytes, layout):
    """Decode one unrotated uniquely captioned raster in its verified PDF coordinate frame."""
    configured = os.environ.get("SCHOLARLENS_TESSERACT", "")
    if not configured or not layout["figure_caption_links"]:
        return []
    exe = Path(configured)
    if not exe.is_absolute() or not exe.is_file() or len(layout["figure_caption_links"]) != 1:
        return []
    (link,) = layout["figure_caption_links"]
    regions = [i for i in layout["items"] if i["locator"] == link["figure_locator"]]
    if len(regions) != 1:
        return []
    box = regions[0]["bbox"]
    try:
        import pypdfium2 as pdfium

        with pdfium.PdfDocument(pdf_bytes) as doc:
            page = doc[layout["page"] - 1]
            if (
                page.get_rotation()
                or abs(page.get_width() - layout["width"]) > 0.03
                or abs(page.get_height() - layout["height"]) > 0.03
            ):
                return []
            objects = list(page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]))
            if len(objects) != 1:
                return []
            (obj,) = objects
            a, b, c, d, _, _ = obj.get_matrix().get()
            x0, y0, x1, y1 = obj.get_bounds()
            bounds = (x0, page.get_height() - y1, x1, page.get_height() - y0)
            w, h = obj.get_px_size()
            if (
                max(abs(actual - expected) for actual, expected in zip(bounds, box)) > 0.03
                or a <= 0
                or d <= 0
                or abs(b) + abs(c) > 0.0001
                or min(w, h) < 48
                or w * h > 3_000_000
            ):
                return []
            image = obj.get_bitmap().to_pil().convert("RGB")
            entries = labels(image, swatch_stack(image), exe)
            if not entries:
                return []
            for entry in entries:
                for kind in ("label", "swatch"):
                    x, y, X, Y = entry[f"{kind}_pixels"]
                    entry[f"{kind}_pdf_bbox"] = [
                        round(v, 3)
                        for v in (
                            box[0] + x * (box[2] - box[0]) / w,
                            box[1] + y * (box[3] - box[1]) / h,
                            box[0] + X * (box[2] - box[0]) / w,
                            box[1] + Y * (box[3] - box[1]) / h,
                        )
                    ]
            return [
                {
                    **link,
                    "page": layout["page"],
                    "paper_id": layout["paper_id"],
                    "source_version": layout["source_version"],
                    "image_size": [w, h],
                    "rgb_sha256": sha256(image.tobytes()).hexdigest(),
                    "entries": entries,
                    "method": "solid_swatch_tesseract_eng",
                }
            ]
    except (ImportError, OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return []
