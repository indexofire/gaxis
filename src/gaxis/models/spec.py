"""ChartSpec — the single intermediate representation shared by every producer.

A spec is produced by three sources (builtin templates, KB adaptation, paper
reproduction) and consumed by exactly one renderer, so "generate a figure" and
"adapt a paper's figure" cannot drift apart.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_FORMATS = ("pdf", "svg", "png", "tiff")


class ChartType(StrEnum):
    bar = "bar"
    stacked_bar = "stacked_bar"
    line = "line"
    scatter = "scatter"
    box = "box"
    heatmap = "heatmap"
    network = "network"
    tree = "tree"


class ChartSpec(BaseModel):
    """Encoding + style intent. Column names must exist in the bound DataSchema."""

    model_config = ConfigDict(extra="forbid")

    chart_type: ChartType = ChartType.bar
    x: str | None = None
    y: str | None = None
    hue: str | None = None
    yerr: str | None = None
    weight: str | None = None
    annotations: list[str] = Field(default_factory=list)
    color_map: dict[str, str] = Field(default_factory=dict)
    rotate_labels: int = Field(default=0, ge=0, le=90)
    title: str | None = None
    xlabel: str | None = None
    ylabel: str | None = None
    preset: str = "default"
    palette: str | None = None
    backend: Literal["python", "r"] = "python"
    width_mm: float | None = Field(default=None, gt=10, le=500)
    height_mm: float | None = Field(default=None, gt=10, le=500)
    dpi: int = Field(default=600, ge=72, le=2400)
    formats: list[str] = Field(default_factory=lambda: ["pdf", "png"])
    annotate_values: bool = False
    notes: str | None = None

    @field_validator("formats")
    @classmethod
    def _check_formats(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one output format is required")
        cleaned = [v.strip().lower() for v in value]
        bad = [v for v in cleaned if v not in ALLOWED_FORMATS]
        if bad:
            raise ValueError(f"unsupported formats {bad}; allowed {list(ALLOWED_FORMATS)}")
        return cleaned

    def encodings(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump(mode="json").items() if v is not None}
