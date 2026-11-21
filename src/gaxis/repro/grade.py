"""Reproduction grading (plan C5): L1 / L2 / L3, with the reason attached.

The level is a claim about non-obvious work, so it is never granted silently:
every branch carries a machine-readable reason that ends up in the manifest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Level = Literal["L1", "L2", "L3", "none"]


@dataclass(frozen=True)
class Grade:
    level: Level
    reason: str


def grade_reproduction(
    *,
    run_ok: bool,
    blocked_reason: str = "",
    similarity: float | None = None,
    l1_threshold: float = 0.85,
    l2_threshold: float = 0.55,
    produces_raster: bool = True,
) -> Grade:
    if blocked_reason:
        return Grade("none", f"not run: {blocked_reason}")
    if not run_ok:
        return Grade("L3", "code does not run as-is: style template only")
    if similarity is None or not produces_raster:
        return Grade(
            "L3",
            "code runs but produced no comparable raster output (vector-only or no image)",
        )
    if similarity >= l1_threshold:
        return Grade("L1", f"runs and reproduces the figure (similarity {similarity:.2f})")
    if similarity >= l2_threshold:
        return Grade(
            "L2",
            f"runs, structurally similar (similarity {similarity:.2f}): "
            "reuse with data/parameter changes",
        )
    return Grade(
        "L3",
        f"runs but visual similarity {similarity:.2f} is below the L2 threshold {l2_threshold:.2f}",
    )
