"""Read trace endpoints using a calibration tied to a specific publisher raster."""

from hashlib import sha256
from math import ceil, floor

from backend.research.figure_legend import pdf_box


def read_pair(pixels, frame, series, ymin, ymax):
    """Require distinct, continuous traces at the final three pixel columns."""
    import numpy as np

    left, top, right, bottom = frame
    if not (
        0 <= left < right - 2 < right < pixels.shape[1]
        and 0 <= top < bottom < pixels.shape[0]
        and ymin < ymax
    ):
        return []
    strip = pixels[top : bottom + 1, right - 2 : right + 1]
    strokes = []
    for name, color in series.items():
        matches = (strip == color).all(axis=2)
        columns = [np.flatnonzero(matches[:, col]) for col in range(3)]
        if any(not 3 <= len(run) <= 8 or run[-1] - run[0] + 1 != len(run) for run in columns):
            return []
        low, high = min(run[0] for run in columns), max(run[-1] for run in columns)
        if high - low > 8 or low <= 1 or high >= bottom - top - 1:
            return []
        strokes.append((int(low) + top, int(high) + top, name, color))

    strokes.sort()
    if any(current[0] - previous[1] < 2 for previous, current in zip(strokes, strokes[1:])):
        return []
    units_per_pixel = (ymax - ymin) / (bottom - top)

    def value(y):
        return ymax - (y - top) * units_per_pixel

    points = []
    for first, last, name, color in strokes:
        # Stroke width plus one pixel for axis registration, rounded outward.
        points.append(
            {
                "series": name,
                "color": "#" + bytes(color).hex(),
                "estimate": round(value((first + last) / 2), 3),
                "interval": [
                    floor(value(last + 1) * 1000) / 1000,
                    ceil(value(first - 1) * 1000) / 1000,
                ],
                "pixel_bbox": [right - 2, first, right + 1, last + 1],
            }
        )
    return points


def chart_readings(layout, raster, profile):
    if raster is None or profile is None:
        return []
    import numpy as np

    image, link, figure_box = raster
    if (
        list(image.size) != profile.size
        or sha256(image.tobytes()).hexdigest() != profile.rgb_sha256
    ):
        return []
    pixels = np.asarray(image)
    panels = []
    for name, frame in profile.panels.items():
        points = read_pair(pixels, frame, profile.colors(), profile.y_axis.min, profile.y_axis.max)
        for point in points:
            point["pdf_bbox"] = pdf_box(point["pixel_bbox"], figure_box, *image.size)
        panels.append(
            {
                "dataset": name,
                "frame_pixels": list(frame),
                "points": points,
                "status": "read" if points else "indistinct_endpoint",
            }
        )
    return [
        {
            **link,
            "source_version": layout["source_version"],
            "paper_id": layout["paper_id"],
            "page": layout["page"],
            "calibration_id": profile.id,
            "rgb_sha256": profile.rgb_sha256,
            "method": "registered_linear_endpoint",
            "x_axis": {**profile.x_axis.model_dump(), "at": profile.x_axis.max},
            "y_axis": profile.y_axis.model_dump(),
            "panels": panels,
        }
    ]
