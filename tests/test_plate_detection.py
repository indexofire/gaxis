"""Multi-figure plates are style references, not single-figure calibration units."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from gaxis.design import analyse_design, apply_plate_policy, plate_like


def _single(path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(3.5, 2.3), dpi=150)
    axis.bar(["A", "B", "C"], [2, 5, 3])
    axis.set_xlabel("group")
    axis.set_ylabel("count")
    figure.savefig(path, facecolor="white")
    plt.close(figure)
    return path


def _plate(path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(3, 1, figsize=(3.5, 7.5), dpi=150)
    for index, axis in enumerate(axes):
        axis.plot([1, 2, 3], [index, index + 2, index + 1])
        axis.set_title(f"Figure {index + 1}")
    figure.subplots_adjust(hspace=0.6)
    figure.savefig(path, facecolor="white")
    plt.close(figure)
    return path


def test_stacked_complete_figures_are_a_plate(tmp_path: Path) -> None:
    assert plate_like(_plate(tmp_path / "plate.png")) is True


def test_single_figure_is_not_a_plate(tmp_path: Path) -> None:
    assert plate_like(_single(tmp_path / "single.png")) is False


def test_plate_policy_clears_score_and_tier(tmp_path: Path) -> None:
    quality = analyse_design(_plate(tmp_path / "plate.png"), caption="Fig 1", label_font_pt=7)
    assert quality.features.plate_like is True
    quality.aesthetic = 0.8
    quality.visualization = 0.7
    quality.score = 0.75
    quality.tier = "gold"
    cleaned = apply_plate_policy(quality, skip_plates=True)
    assert cleaned.archetype == "plate"
    assert cleaned.score is None
    assert cleaned.tier is None
    assert cleaned.aesthetic is None
    assert "style reference" in cleaned.notes[0]


def test_policy_is_off_by_request(tmp_path: Path) -> None:
    quality = analyse_design(_plate(tmp_path / "plate.png"), caption="", label_font_pt=7)
    quality.score = 0.75
    kept = apply_plate_policy(quality, skip_plates=False)
    assert kept.score == 0.75
    assert kept.archetype == "plate"
