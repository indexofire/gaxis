"""Visual comparison and grading thresholds."""

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from gaxis.repro.compare import compare_images, raster_candidates
from gaxis.repro.grade import grade_reproduction


def _png(path: Path, *, bars: list[int], size=(320, 200)) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(size[0] / 100, size[1] / 100), dpi=100)
    axis.bar(["A", "B", "C"], bars, color="#009E73")
    axis.set_ylim(0, 10)
    figure.savefig(path)
    plt.close(figure)
    return path


def test_identical_images_score_high(tmp_path: Path) -> None:
    reference = _png(tmp_path / "ref.png", bars=[2, 5, 8])
    report = compare_images(reference, reference)
    assert report.score > 0.95
    assert report.components["correlation"] > 0.99


def test_different_figures_score_low(tmp_path: Path) -> None:
    reference = _png(tmp_path / "ref.png", bars=[2, 5, 8])
    other = _png(tmp_path / "other.png", bars=[9, 1, 4])
    report = compare_images(reference, other)
    assert report.score < 0.9
    assert report.score < compare_images(reference, reference).score


def test_aspect_ratio_mismatch_is_penalised(tmp_path: Path) -> None:
    reference = _png(tmp_path / "ref.png", bars=[2, 5, 8])
    wide = _png(tmp_path / "wide.png", bars=[2, 5, 8], size=(420, 120))
    narrow = _png(tmp_path / "narrow.png", bars=[2, 5, 8])
    assert compare_images(reference, wide).score < compare_images(reference, narrow).score


def test_raster_candidates_filter_non_images(tmp_path: Path) -> None:
    paths = [tmp_path / "a.png", tmp_path / "b.pdf", tmp_path / "c.csv", tmp_path / "d.jpg"]
    assert [p.name for p in raster_candidates(paths)] == ["a.png", "d.jpg"]


def test_grading_branches_are_explicit() -> None:
    assert grade_reproduction(run_ok=True, similarity=0.92).level == "L1"
    assert grade_reproduction(run_ok=True, similarity=0.70).level == "L2"
    low = grade_reproduction(run_ok=True, similarity=0.20)
    assert low.level == "L3"
    assert "below the L2 threshold" in low.reason
    blocked = grade_reproduction(run_ok=False, blocked_reason="static scan blocked the run")
    assert blocked.level == "none"
    assert blocked.reason.startswith("not run")
    no_raster = grade_reproduction(run_ok=True, similarity=None, produces_raster=False)
    assert no_raster.level == "L3"
    failed = grade_reproduction(run_ok=False)
    assert failed.level == "L3"
