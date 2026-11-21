"""Composition manifest: a multi-panel figure assembled from rendered panels.

Vector panels are placed onto one page with PyMuPDF, so the output stays editable and
each panel keeps its own code/manifest as evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from .. import __version__
from .lint import LintReport


class PanelRef(BaseModel):
    manifest_id: str
    label: str = ""
    source_file: str
    code_sha256: str = ""


class CompositionManifest(BaseModel):
    composition_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    panels: list[PanelRef]
    layout: tuple[int, int]
    preset: str
    width_mm: float
    height_mm: float
    output_pdf: str
    output_png: str | None = None
    uniform: bool = False
    lint: LintReport = Field(default_factory=LintReport)
    generator: str = f"gaxis {__version__}"
