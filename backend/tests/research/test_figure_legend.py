from hashlib import sha256
from types import SimpleNamespace

from PIL import Image, ImageDraw
import pytest

from backend.research.figure_legend import labels, page_legends, swatch_stack


def fixture(positions=(17, 31, 45), colors=("red", "blue", "green"), x=19):
    image = Image.new("RGB", (260, 155), "white")
    draw = ImageDraw.Draw(image)
    for y, color in zip(positions, colors):
        draw.rectangle([x, y, x + 28, y + 8], fill=color)
    return image


@pytest.mark.parametrize("x", [19, 127])
def test_locates_stack_in_either_half(x):
    stack = swatch_stack(fixture(x=x))
    assert stack == [
        (x, 17, x + 29, 26, "#ff0000"),
        (x, 31, x + 29, 40, "#0000ff"),
        (x, 45, x + 29, 54, "#008000"),
    ]


def test_rejects_repeated_colours_uneven_spacing_and_two_stacks():
    assert not swatch_stack(fixture(colors=("red", "blue", "red")))
    assert not swatch_stack(fixture(positions=(7, 31, 45)))
    image = fixture()
    draw = ImageDraw.Draw(image)
    for y, c in zip((17, 31, 45), ("yellow", "purple", "aqua")):
        draw.rectangle([168, y, 196, y + 8], fill=c)
    assert not swatch_stack(image)


@pytest.mark.parametrize("bad", ["none", "low", "misplaced", "repeat", "gap", "partial"])
def test_label_requires_one_local_text_group_per_swatch(monkeypatch, bad):
    image = fixture()
    stack = swatch_stack(image)
    header = "level\tleft\ttop\twidth\theight\tconf\ttext\n"
    # Coordinates in the padded text tile. Labels start next to each swatch.
    records = [
        [5, 15, 17, 16, 7, 95, "River"],
        [5, 15, 31, 16, 7, 96, "Lake"],
        [5, 15, 45, 14, 7, 91, "Sea"],
    ]
    if bad == "low":
        records[1][5] = 32
    if bad == "misplaced":
        records[1][2] += 8
    if bad == "repeat":
        records[1][-1] = "River"
    if bad == "gap":
        records.append([5, 60, 17, 16, 7, 91, "Stone"])
    if bad == "partial":
        records.pop()
    response = header + "".join("\t".join(map(str, r)) + "\n" for r in records)
    monkeypatch.setattr(
        "backend.research.figure_legend.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=response.encode()),
    )
    result = labels(image, stack, "test-engine")
    if bad == "none":
        assert [e["text"] for e in result] == ["River", "Lake", "Sea"]
        assert result[0]["text_sha256"] == sha256(b"River").hexdigest()
        assert result[0]["label_pixels"] == [52, 18, 68, 25]
    else:
        assert result == []


def test_legend_ocr_is_optional(monkeypatch):
    monkeypatch.delenv("SCHOLARLENS_TESSERACT", raising=False)
    assert page_legends(b"", {}) == []
    monkeypatch.setenv("SCHOLARLENS_TESSERACT", "relative.exe")
    assert page_legends(b"", {"figure_caption_links": [{}]}) == []
