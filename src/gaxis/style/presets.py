"""Journal presets: geometry in millimetres, type in points, fonts with fallbacks.

Microbiology first (Nature Microbiology, ASM/mBio, ISME J, Cell Host & Microbe,
Microbial Genomics), with ``nature`` and ``default`` as generic fallbacks.
"""

from __future__ import annotations

import tomllib
from functools import cache, lru_cache
from importlib import resources
from typing import Any

from pydantic import BaseModel, Field

from ..models.spec import ChartSpec


class Preset(BaseModel):
    name: str
    label: str
    description: str = ""
    publisher: str = ""
    width_single_mm: float = Field(gt=10, le=250)
    width_double_mm: float = Field(gt=10, le=500)
    height_mm: float = Field(gt=10, le=400)
    height_double_mm: float = Field(gt=10, le=400)
    base_font_pt: float = Field(ge=4, le=24)
    label_font_pt: float = Field(ge=4, le=24)
    title_font_pt: float = Field(ge=4, le=24)
    line_width_pt: float = Field(default=0.5, gt=0)
    spine_width_pt: float = Field(default=0.5, gt=0)
    marker_size_pt: float = Field(default=3.0, gt=0)
    dpi: int = Field(default=600, ge=300, le=2400)
    font_family: list[str] = Field(default_factory=lambda: ["Arial", "Liberation Sans"])
    palette: str = "okabe_ito"
    legend_frame: bool = False
    grid: bool = False
    spines: list[str] = Field(default_factory=lambda: ["left", "bottom"])
    vector_required: bool = True


def _preset_dir() -> resources.abc.Traversable:
    return resources.files("gaxis.style").joinpath("journal_presets")


@lru_cache(maxsize=1)
def preset_names() -> list[str]:
    names = sorted(
        str(p.name).removesuffix(".toml")
        for p in _preset_dir().iterdir()
        if str(p.name).endswith(".toml")
    )
    if not names:
        raise RuntimeError("no journal presets found in gaxis/style/presets")
    return names


@cache
def load_preset(name: str) -> Preset:
    key = name.strip().lower()
    if key not in preset_names():
        raise KeyError(f"unknown preset '{name}'; available: {preset_names()}")
    raw: dict[str, Any] = tomllib.loads((_preset_dir() / f"{key}.toml").read_text(encoding="utf-8"))
    raw.setdefault("name", key)
    raw.setdefault("label", key)
    return Preset(**raw)


def default_preset() -> Preset:
    return load_preset("default")


def resolve_size(spec: ChartSpec, preset: Preset) -> tuple[float, float]:
    """Return (width_mm, height_mm); double-column width implies double-column height."""
    width = spec.width_mm or preset.width_single_mm
    if spec.height_mm:
        height = spec.height_mm
    elif width > preset.width_single_mm * 1.15:
        height = preset.height_double_mm
    else:
        height = preset.height_mm
    return float(width), float(height)


def preset_table() -> list[dict[str, Any]]:
    return [
        {
            "name": p.name,
            "label": p.label,
            "publisher": p.publisher,
            "single_mm": f"{p.width_single_mm:g}x{p.height_mm:g}",
            "double_mm": f"{p.width_double_mm:g}x{p.height_double_mm:g}",
            "font_pt": f"{p.base_font_pt:g}",
            "dpi": p.dpi,
            "palette": p.palette,
        }
        for p in (load_preset(n) for n in preset_names())
    ]
