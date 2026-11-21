"""Usefulness: is this figure worth reproducing at all?

Design quality answers "is it well made". Usefulness answers "is it the kind of figure a
microbiologist would reuse" — journal tier, evidence signals, panel richness, caption
completeness, and whether the code has been verified. Retrieval ranks by
``design.score * usefulness.score``, so a beautiful but trivial figure does not beat a
well-made figure from a strong venue with statistics.

Everything here is deterministic and explainable; the weights live in ``[usefulness]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models.paper import ChartReproManifest

# Venue is deliberately compressed: it is a tie-breaker, not the driver. Design quality
# decides whether a figure is good; venue only nudges between comparable figures.
JOURNAL_TIERS: dict[str, tuple[float, str]] = {
    "10.1038": (1.00, "Nature Portfolio"),
    "10.1126": (1.00, "Science"),
    "10.1016": (0.95, "Elsevier (Cell Press family)"),
    "10.1128": (0.92, "ASM journals"),
    "10.1093": (0.90, "Oxford (FEMS/ISME family)"),
    "10.1099": (0.88, "Microbiology Society"),
    "10.1186": (0.85, "BMC"),
    "10.1371": (0.82, "PLOS"),
    "10.1101": (0.72, "bioRxiv preprint"),
    "10.21203": (0.72, "Research Square preprint"),
}

_PANEL_RANGE = re.compile(r"panel[s]?\s+([a-h])(?:\s*[-\u2013]\s*([a-h]))?", re.IGNORECASE)
_SINGLE_PANEL = re.compile(r"\b([a-h])\)", re.IGNORECASE)


@dataclass(frozen=True)
class UsefulnessWeights:
    journal: float = 0.20
    statistics: float = 0.25
    verification: float = 0.25
    panels: float = 0.20
    caption: float = 0.10

    def as_dict(self) -> dict[str, float]:
        return {
            "journal": self.journal,
            "statistics": self.statistics,
            "verification": self.verification,
            "panels": self.panels,
            "caption": self.caption,
        }


def journal_tier(doi: str | None) -> tuple[float, str]:
    if not doi:
        return 0.85, "unknown venue"
    lowered = doi.lower()
    for prefix, (score, label) in JOURNAL_TIERS.items():
        if lowered.startswith(prefix):
            return score, label
    return 0.85, "unmapped venue"


def panel_count(caption: str) -> int:
    lowered = caption or ""
    match = _PANEL_RANGE.search(lowered)
    if match:
        start = ord(match.group(1).lower())
        end = ord(match.group(2).lower()) if match.group(2) else start
        if end >= start:
            return min(8, end - start + 1)
    markers = {single.group(1).lower() for single in _SINGLE_PANEL.finditer(lowered)}
    return max(1, min(8, len(markers)))


def _statistics_score(manifest: ChartReproManifest) -> float:
    design = manifest.design
    signals = set(design.features.caption_signals) if design else set()
    score = 0.0
    if "uncertainty" in signals:
        score += 0.5
    if "sample_size" in signals:
        score += 0.3
    if "units" in signals:
        score += 0.2
    return min(1.0, score)


def _verification_score(manifest: ChartReproManifest) -> float:
    return {
        "L1": 1.0,
        "L2": 0.7,
        "L3": 0.3,
        "none": 0.2,
    }.get(manifest.reproduction.level, 0.2)


def usefulness_components(manifest: ChartReproManifest) -> dict[str, float]:
    tier, _label = journal_tier(manifest.doi)
    panels = panel_count(manifest.caption)
    return {
        "journal": tier,
        "statistics": _statistics_score(manifest),
        "verification": _verification_score(manifest),
        "panels": min(1.0, panels / 4.0),
        "caption": 1.0
        if len(manifest.caption) > 200
        else 0.6
        if len(manifest.caption) > 80
        else 0.3,
        "panel_count": float(panels),
    }


def score_usefulness(
    manifest: ChartReproManifest, weights: UsefulnessWeights | None = None
) -> float:
    weights = weights or UsefulnessWeights()
    components = usefulness_components(manifest)
    total = sum(weights.as_dict().values()) or 1.0
    raw = sum(getattr(weights, name) * components.get(name, 0.0) for name in weights.as_dict())
    return round(max(0.0, min(1.0, raw / total)), 4)


def usefulness_notes(
    manifest: ChartReproManifest, weights: UsefulnessWeights | None = None
) -> list[str]:
    _tier, label = journal_tier(manifest.doi)
    components = usefulness_components(manifest)
    notes = [
        f"venue: {label}",
        f"panels: {int(components['panel_count'])}",
        f"verification: {manifest.reproduction.level}",
    ]
    design = manifest.design
    if design and design.features.caption_signals:
        notes.append("signals: " + ", ".join(design.features.caption_signals))
    return notes
