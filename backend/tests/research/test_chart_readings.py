import numpy as np
import pytest
import json

from backend.research.chart_readings import read_pair
from backend.research.chart_registry import BUILTIN, LIMIT, read_registry


FRAME = (2, 2, 36, 32)
SERIES = {"Cold": (0, 10, 244), "Warm": (128, 0, 16)}


def bitmap():
    image = np.full((40, 42, 3), 255, dtype="uint8")
    image[7:10, 5:37] = SERIES["Cold"]
    image[19:22, 5:37] = SERIES["Warm"]
    return image


def test_calibrated_linear_endpoint():
    points = read_pair(bitmap(), FRAME, SERIES, 10, 70)
    assert [(v["series"], v["estimate"]) for v in points] == [("Cold", 58), ("Warm", 34)]
    assert points[0]["pixel_bbox"] == [34, 7, 37, 10]
    assert points[0]["interval"] == [54, 62]


@pytest.mark.parametrize(
    "case", ["empty", "last_missing", "duplicate_band", "touching", "unregistered"]
)
def test_abstains_when_pair_or_calibration_is_ambiguous(case):
    image = bitmap()
    if case == "empty":
        image[:] = 255
    if case == "last_missing":
        image[7:10, 36] = 255
    if case == "duplicate_band":
        image[13:16, 34:37] = SERIES["Cold"]
    if case == "touching":
        image[19:22] = 255
        image[10:13, 34:37] = SERIES["Warm"]
    if case == "unregistered":
        assert not read_pair(image, (2, 2, 45, 32), SERIES, 10, 70)
    else:
        assert not read_pair(image, FRAME, SERIES, 10, 70)


@pytest.mark.parametrize(
    "bad",
    [
        "duplicate",
        "digest",
        "version",
        "bounds",
        "size",
        "panels_limit",
        "nan",
        "axis_order",
        "order",
        "extra",
        "color",
        "file_limit",
        "duplicate_key",
    ],
)
def test_bounded_registry_rejects_invalid_data(tmp_path, bad):
    data = json.loads(BUILTIN.read_bytes())
    profile = data["profiles"][0]
    if bad == "duplicate":
        data["profiles"].append(profile)
    elif bad == "digest":
        profile["rgb_sha256"] = "arbitrary"
    elif bad == "version":
        data["version"] = True
    elif bad == "bounds":
        profile["panels"] = {"bad": [2, 4, 1900, 120]}
    elif bad == "size":
        profile["size"] = [2100, 2100]
    elif bad == "panels_limit":
        profile["panels"] = {str(i): [0, 0, 60, 70] for i in range(33)}
    elif bad == "nan":
        profile["y_axis"]["min"] = float("nan")
    elif bad == "axis_order":
        profile["x_axis"]["max"] = -5
    elif bad == "order":
        profile["panels"] = {"a": [60, 10, 10, 30]}
    elif bad == "extra":
        profile["values"] = [15]
    elif bad == "color":
        profile["series"] = {"a": "#008455", "b": "#008455"}
    text = json.dumps(data)
    if bad == "file_limit":
        text += " " * LIMIT
    if bad == "duplicate_key":
        text = '{"version":1,"version":1,"profiles":[]}'
    path = tmp_path / "registry.json"
    path.write_text(text, encoding="utf8")
    with pytest.raises(ValueError):
        read_registry(path)


def test_independent_pdf_with_new_operator_calibration(tmp_path):
    from tools.research_eval.v7_chart_fresh import evaluate

    result = evaluate(tmp_path)
    assert result["known_values"] == {"Canal": 56, "Pool": -1}
