"""FigureManifest — every delivered artifact bound to its inputs (ADR-08)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from .. import __version__
from .lint import LintReport
from .schema import DataSchema
from .spec import ChartSpec

FigureSource = Literal["builtin_templates", "kb_asset", "paper_reproduction", "figure_recipe"]


class OutputFile(BaseModel):
    path: str
    format: str
    bytes: int
    width_mm: float | None = None
    height_mm: float | None = None
    dpi: int | None = None


class FigureManifest(BaseModel):
    figure_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    spec: ChartSpec
    data: DataSchema
    preset: str
    backend: Literal["python", "r"]
    style: dict[str, object] = Field(default_factory=dict)
    code_path: str
    code_sha256: str
    outputs: list[OutputFile] = Field(default_factory=list)
    lint: LintReport = Field(default_factory=LintReport)
    source: FigureSource = "builtin_templates"
    recipe_id: str | None = None
    asset_ids: list[str] = Field(default_factory=list)
    generator: str = f"gaxis {__version__}"
