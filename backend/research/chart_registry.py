"""Validate the bounded operator-owned registry of linear chart calibrations."""

import json
import os
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

BUILTIN = Path(__file__).with_name("calibrations") / "linear-endpoints-v1.json"
LIMIT = 128 * 1024
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Label = Annotated[str, Field(max_length=80, min_length=1, pattern=r"^[^\p{C}]+$")]
Color = Annotated[str, Field(pattern=r"^#[0-9a-f]{6}$")]
Pixel = Annotated[int, Field(ge=0, le=8192)]
Coordinate = Annotated[float, Field(ge=-1e9, le=1e9, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Axis(StrictModel):
    label: Label
    min: Coordinate
    max: Coordinate

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.max - self.min < 0.001:
            raise ValueError("axis range too small for three decimal places")
        return self


class Profile(StrictModel):
    id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")]
    source_version: Digest
    rgb_sha256: Digest
    caption_sha256: Digest
    page: Annotated[int, Field(ge=1, le=500)]
    figure: Annotated[int, Field(ge=1, le=9999)]
    size: Annotated[list[Pixel], Field(min_length=2, max_length=2)]
    x_axis: Axis
    y_axis: Axis
    panels: Annotated[
        dict[Label, Annotated[list[Pixel], Field(min_length=4, max_length=4)]],
        Field(min_length=1, max_length=32),
    ]
    series: Annotated[dict[Label, Color], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def geometry(self) -> Self:
        width, height = self.size
        if min(width, height) < 48 or width * height > 3_000_000:
            raise ValueError("unsupported image dimensions")
        if len(set(self.series.values())) != len(self.series):
            raise ValueError("ambiguous series colors")
        frames = list(self.panels.values())
        for i, (left, top, right, bottom) in enumerate(frames):
            if not (left + 2 < right < width and top + 8 < bottom < height):
                raise ValueError("frame must fit the calibrated bitmap")
            if any(
                max(left, a) < min(right, c) and max(top, b) < min(bottom, d)
                for a, b, c, d in frames[:i]
            ):
                raise ValueError("overlapping frames")
        return self

    def colors(self):
        return {name: tuple(bytes.fromhex(color[1:])) for name, color in self.series.items()}


class Registry(StrictModel):
    version: Literal[1]
    profiles: Annotated[list[Profile], Field(max_length=32)]

    @model_validator(mode="after")
    def unique(self) -> Self:
        keys = {(p.source_version, p.page, p.figure) for p in self.profiles}
        if len(keys) != len(self.profiles) or len({p.id for p in self.profiles}) != len(keys):
            raise ValueError("duplicate chart registration")
        return self


def unique_keys(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate calibration field")
    return result


def read_registry(path):
    if not path.is_absolute() or str(path).startswith(("//", "\\\\")) or not path.is_file():
        raise ValueError("expected local regular file")
    with path.open("rb") as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("oversized chart registry")
    parsed = json.loads(data.decode("utf8"), object_pairs_hook=unique_keys)
    if not isinstance(parsed, dict) or type(parsed.get("version")) is not int:
        raise ValueError("invalid chart registry version")
    return Registry.model_validate(parsed)


def lookup(layout):
    links = layout["figure_caption_links"]
    if len(links) != 1:
        return "no_unique_figure", None
    path = Path(os.getenv("SCHOLARLENS_CHART_CALIBRATIONS") or BUILTIN)
    try:
        registry = read_registry(path)
    except (OSError, ValueError, RecursionError):
        return "registry_unavailable", None
    link = links[0]
    for profile in registry.profiles:
        if (profile.source_version, profile.page, profile.figure, profile.caption_sha256) == (
            layout["source_version"],
            layout["page"],
            link["number"],
            link["caption_quote_sha256"],
        ):
            return "registered", profile
    return "unregistered", None
