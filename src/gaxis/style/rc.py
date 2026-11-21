"""Preset -> matplotlib rcParams. Font resolution degrades explicitly, never silently."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .presets import Preset

MM_PER_INCH = 25.4


def _font_manager() -> Any:
    from matplotlib import font_manager

    return font_manager


@lru_cache(maxsize=1)
def available_fonts() -> frozenset[str]:
    return frozenset(f.name for f in _font_manager().fontManager.ttflist)


@lru_cache(maxsize=64)
def resolve_font(families: tuple[str, ...]) -> str | None:
    """Return the first installed family, matching case-insensitively."""
    lookup = {name.lower(): name for name in available_fonts()}
    for family in families:
        found = lookup.get(family.lower())
        if found:
            return found
    return None


def size_inches(width_mm: float, height_mm: float) -> tuple[float, float]:
    return width_mm / MM_PER_INCH, height_mm / MM_PER_INCH


def build_rc(
    preset: Preset,
    *,
    width_mm: float,
    height_mm: float,
    dpi: int,
) -> dict[str, Any]:
    """Complete rcParams dict for the preset. Emitted verbatim into generated code."""
    font = resolve_font(tuple(preset.font_family)) or "DejaVu Sans"
    family_chain = [
        font,
        *[f for f in preset.font_family if f.lower() != font.lower()],
        "DejaVu Sans",
    ]
    spines = {s.lower() for s in preset.spines}
    return {
        "font.family": "sans-serif",
        "font.sans-serif": family_chain,
        "font.size": preset.base_font_pt,
        "axes.labelsize": preset.label_font_pt,
        "axes.titlesize": preset.title_font_pt,
        "xtick.labelsize": preset.base_font_pt,
        "ytick.labelsize": preset.base_font_pt,
        "legend.fontsize": preset.base_font_pt,
        "legend.title_fontsize": preset.base_font_pt,
        "figure.titlesize": preset.title_font_pt,
        "lines.linewidth": preset.line_width_pt,
        "lines.markersize": preset.marker_size_pt,
        "patch.linewidth": preset.spine_width_pt,
        "axes.linewidth": preset.spine_width_pt,
        "axes.edgecolor": "#000000",
        "axes.labelcolor": "#000000",
        "text.color": "#000000",
        "xtick.color": "#000000",
        "ytick.color": "#000000",
        "xtick.major.width": preset.spine_width_pt,
        "ytick.major.width": preset.spine_width_pt,
        "xtick.minor.width": preset.spine_width_pt * 0.8,
        "ytick.minor.width": preset.spine_width_pt * 0.8,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "axes.spines.top": "top" in spines,
        "axes.spines.right": "right" in spines,
        "axes.grid": preset.grid,
        "grid.linewidth": 0.3,
        "grid.alpha": 0.4,
        "legend.frameon": preset.legend_frame,
        "legend.framealpha": 1.0,
        "figure.figsize": size_inches(width_mm, height_mm),
        "figure.dpi": 150,
        "savefig.dpi": dpi,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.01,
        "savefig.transparent": False,
        # Embedded TrueType (Type 42) is required by most journals; Type 3 is rejected.
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "svg.hashsalt": "gaxis",
    }
