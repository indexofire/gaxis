"""Offline regression for the design judge: the golden set must stay separable.

Network-free: it replays judgements cached in tests/data/golden_design_judgements.json.
Refresh that file only after an intentional prompt/model change, and record the reason.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CACHE = Path(__file__).parent / "data" / "golden_design_judgements.json"


@pytest.fixture(scope="module")
def records() -> list[dict]:
    return json.loads(CACHE.read_text())["records"]


def test_golden_set_is_separable(records: list[dict]) -> None:
    good = [r["score"] for r in records if r["label"] == "good"]
    bad = [r["score"] for r in records if r["label"] == "bad"]
    assert len(good) >= 20
    assert len(bad) >= 5

    wins = sum(1 for g in good for b in bad if g > b) + 0.5 * sum(
        1 for g in good for b in bad if g == b
    )
    auc = wins / (len(good) * len(bad))
    assert auc >= 0.9, f"AUC dropped to {auc:.3f}"

    good_mean = sum(good) / len(good)
    bad_mean = sum(bad) / len(bad)
    assert good_mean - bad_mean >= 0.2
    assert max(bad) <= 0.5, "a counterexample scored in the acceptable range"


def test_judge_records_are_explainable(records: list[dict]) -> None:
    for record in records:
        assert record["aesthetic"] is not None
        assert record["visualization"] is not None
        assert 0.0 <= record["score"] <= 1.0
