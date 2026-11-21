"""Regression: the design judge must separate owner-kept figures from rejected ones."""

from __future__ import annotations

import json
from pathlib import Path

CACHE = Path(__file__).parent / "data" / "single_figure_judgements.json"


def _records() -> list[dict]:
    return json.loads(CACHE.read_text())["records"]


def test_rubric_v3_separates_kept_from_dropped() -> None:
    records = _records()
    keep = [r["score"] for r in records if r["label"] == "keep"]
    drop = [r["score"] for r in records if r["label"] == "drop"]
    assert len(keep) >= 5
    assert len(drop) >= 5

    wins = sum(1 for a in keep for b in drop if a > b) + 0.5 * sum(
        1 for a in keep for b in drop if a == b
    )
    auc = wins / (len(keep) * len(drop))
    assert auc >= 0.90, f"AUC regressed to {auc:.3f} (0.937 with rubric v3.1)"

    assert sum(keep) / len(keep) - sum(drop) / len(drop) >= 0.2


def test_every_judged_case_has_a_category() -> None:
    for record in _records():
        assert record["category"] in {
            "chart",
            "mixed",
            "plate",
            "schematic",
            "micrograph",
            "unknown",
        }
