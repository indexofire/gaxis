"""Colour palettes. The default is colour-blind safe (Okabe-Ito)."""

from __future__ import annotations

from pydantic import BaseModel

OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#000000"]
NPG = ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4", "#91D1C2", "#DC0000"]
SET2 = ["#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3", "#A6D854", "#FFD92F", "#E5C494", "#B3B3B3"]
VIRIDIS = ["#440154", "#46327E", "#365C8D", "#277F8E", "#1FA187", "#4AC16D", "#A0DA39", "#FDE725"]
GREYS = ["#1A1A1A", "#4D4D4D", "#808080", "#B3B3B3", "#D9D9D9", "#F2F2F2"]


class Palette(BaseModel):
    name: str
    colors: list[str]
    colorblind_safe: bool
    description: str = ""


PALETTES: dict[str, Palette] = {
    p.name: p
    for p in [
        Palette(
            name="okabe_ito",
            colors=OKABE_ITO,
            colorblind_safe=True,
            description="Okabe-Ito: deuteranopia/protanopia safe, Nature-recommended default",
        ),
        Palette(
            name="npg", colors=NPG, colorblind_safe=False, description="Nature Publishing Group"
        ),
        Palette(name="set2", colors=SET2, colorblind_safe=False, description="ColorBrewer Set2"),
        Palette(
            name="viridis",
            colors=VIRIDIS,
            colorblind_safe=True,
            description="Viridis: perceptually uniform, print safe",
        ),
        Palette(
            name="greys", colors=GREYS, colorblind_safe=True, description="Greyscale for mono print"
        ),
    ]
}

DEFAULT_PALETTE = "okabe_ito"


def get_palette(name: str | None) -> Palette:
    key = (name or DEFAULT_PALETTE).strip().lower()
    if key not in PALETTES:
        raise KeyError(f"unknown palette '{name}'; available: {sorted(PALETTES)}")
    return PALETTES[key]


def palette_names() -> list[str]:
    return sorted(PALETTES)
