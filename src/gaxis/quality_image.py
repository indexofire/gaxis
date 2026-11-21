"""Crop-quality heuristics: is this crop a figure, or a slice of body text?

The other components are metadata; this one looks at the pixels. It is deliberately
crude and explainable, and it exists because homogeneous paper corpora made every
asset score the same — the score needs a component that can disagree.

Signals (all on a 600-px grayscale/RGB reduction):

    blank      almost no ink                          -> useless crop
    text       many thin, evenly-inked rows           -> body text or caption
    clipped    heavy ink on the outer frame           -> figure cut off
    tinted     large light-but-coloured background    -> scanned page / highlighter
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_SIDE = 600


@dataclass(frozen=True)
class CropReport:
    score: float
    ink_ratio: float
    short_run_ratio: float
    row_periodicity: float
    line_bands: int
    band_height_cv: float
    border_ink: float
    tint_ratio: float
    verdict: str

    def as_dict(self) -> dict[str, float | str]:
        return {
            "score": round(self.score, 3),
            "ink_ratio": round(self.ink_ratio, 4),
            "short_run_ratio": round(self.short_run_ratio, 4),
            "row_periodicity": round(self.row_periodicity, 4),
            "line_bands": self.line_bands,
            "band_height_cv": round(self.band_height_cv, 4),
            "border_ink": round(self.border_ink, 4),
            "tint_ratio": round(self.tint_ratio, 4),
            "verdict": self.verdict,
        }


def _load(source: bytes | Path) -> tuple[Any, Any]:
    import numpy as np
    from PIL import Image

    image = Image.open(io.BytesIO(source)) if isinstance(source, bytes) else Image.open(source)
    with image:
        rgb = image.convert("RGB")
        scale = MAX_SIDE / max(rgb.size)
        if scale < 1:
            rgb = rgb.resize((max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale))))
        gray = np.asarray(rgb.convert("L"), dtype="float32") / 255.0
        colour = np.asarray(rgb, dtype="float32") / 255.0
    return gray, colour


def _short_run_ratio(ink: Any) -> float:
    """Share of ink inside thin horizontal runs — text is made of short strokes."""
    import numpy as np

    limit = max(3, int(0.025 * ink.shape[1]))
    short = 0.0
    total = 0.0
    for row in ink:
        edges = np.flatnonzero(np.diff(np.concatenate(([0], row.astype("int8"), [0]))))
        lengths = edges[1::2] - edges[0::2]
        total += float(lengths.sum())
        short += float(lengths[lengths < limit].sum())
    return short / total if total else 0.0


def _row_periodicity(ink: Any) -> float:
    """Text lines repeat with a baseline rhythm; charts do not."""

    profile = ink.mean(axis=1)
    profile = profile - profile.mean()
    denominator = float((profile**2).sum()) or 1.0
    best = 0.0
    for lag in range(5, min(61, len(profile))):
        best = max(best, float((profile[:-lag] * profile[lag:]).sum() / denominator))
    return max(0.0, best)


def _line_bands(ink: Any) -> tuple[int, float, float]:
    """(band count, height CV, blank-row ratio) — body text is many equal-height bands."""
    import numpy as np

    inked_rows = ink.mean(axis=1) > 0.001
    edges = np.flatnonzero(np.diff(np.concatenate(([0], inked_rows.astype("int8"), [0]))))
    heights = edges[1::2] - edges[0::2]
    blank_ratio = float(1.0 - inked_rows.mean())
    if not len(heights):
        return 0, 0.0, blank_ratio
    mean = float(heights.mean())
    cv = float(heights.std() / mean) if mean else 0.0
    return len(heights), cv, blank_ratio


def analyse_crop(source: bytes | Path) -> CropReport:
    import numpy as np

    gray, colour = _load(source)
    height, width = gray.shape
    ink = gray < 0.85
    ink_ratio = float(ink.mean())
    short_run_ratio = _short_run_ratio(ink)
    row_periodicity = _row_periodicity(ink)
    line_bands, band_height_cv, blank_ratio = _line_bands(ink)

    frame = max(2, round(min(height, width) * 0.02))
    border = np.concatenate(
        [
            ink[:frame, :].ravel(),
            ink[-frame:, :].ravel(),
            ink[:, :frame].ravel(),
            ink[:, -frame:].ravel(),
        ]
    )
    border_ink = float(border.mean())

    brightness = colour.max(axis=2)
    saturation = colour.max(axis=2) - colour.min(axis=2)
    light = brightness > 0.82
    tint_ratio = float((light & (saturation > 0.12)).mean())

    score = 1.0
    verdict = "ok"

    def report(score_value: float, verdict_value: str) -> CropReport:
        return CropReport(
            score=round(max(0.0, min(1.0, score_value)), 3),
            ink_ratio=ink_ratio,
            short_run_ratio=short_run_ratio,
            row_periodicity=row_periodicity,
            line_bands=line_bands,
            band_height_cv=band_height_cv,
            border_ink=border_ink,
            tint_ratio=tint_ratio,
            verdict=verdict_value,
        )

    if ink_ratio < 0.005:
        return report(0.0, "blank")
    # Body text: many horizontal bands of equal height, separated by blank rows.
    # Thin-stroke figures (trees, line charts) fail the band test even though their
    # run lengths look text-like, so this stays a text detector, not a "thin" detector.
    if line_bands >= 6 and band_height_cv < 0.2 and blank_ratio > 0.2 and short_run_ratio > 0.8:
        score -= 0.65
        verdict = "text"
    if border_ink > 0.18:
        score -= 0.25
        verdict = "clipped" if verdict == "ok" else f"{verdict}+clipped"
    # A coloured background inside the artwork (gel photos, heatmaps) is content, not a
    # defect. Only sparse ink on a large tinted field reads as a scanned page.
    if tint_ratio > 0.35 and ink_ratio < 0.1:
        score -= 0.2
        verdict = "tinted" if verdict == "ok" else f"{verdict}+tinted"
    return report(score, verdict)


def crop_clean_score(source: bytes | Path) -> float:
    return analyse_crop(source).score
