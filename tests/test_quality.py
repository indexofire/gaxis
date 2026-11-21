"""Quality scoring, Spearman, calibration, and the human-ranking sheet."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaxis.models.paper import ChartReproManifest
from gaxis.quality import (
    CalibrationRow,
    QualityWeights,
    build_sheet,
    calibrate,
    design_tier,
    score_components,
    score_manifest,
    spearman,
)

from .manifest_factory import make_manifest


def test_full_evidence_scores_one_and_caption_only_is_capped() -> None:
    rich = make_manifest(level="L1")
    assert score_manifest(rich, QualityWeights()) == pytest.approx(1.0)

    caption_only = make_manifest(image="", quality=0.0)
    caption_only.geometry = None
    caption_only.citing_paragraph = ""
    score = score_manifest(caption_only, QualityWeights())
    assert 0.2 <= score <= 0.4


def test_weights_are_normalised_so_relative_importance_is_what_matters() -> None:
    base = {
        "caption": 0.28,
        "artwork": 0.18,
        "resolution": 0.14,
        "area": 0.09,
        "vector": 0.13,
        "cited": 0.08,
        "crop_clean": 0.10,
    }
    doubled = {key: value * 2 for key, value in base.items()}
    components = dict.fromkeys(base, 1.0)
    assert score_components(components, QualityWeights(**base)) == pytest.approx(
        score_components(components, QualityWeights(**doubled))
    )


def test_spearman_detects_agreement_and_inversion() -> None:
    a = [1, 2, 3, 4, 5]
    assert spearman(a, a) == pytest.approx(1.0)
    assert spearman(a, list(reversed(a))) == pytest.approx(-1.0)
    assert spearman([1, 1, 1, 1], a) == pytest.approx(0.0)
    assert spearman([1, 2], [1, 2]) == 0.0  # too few samples


def test_calibration_moves_weights_towards_the_signal() -> None:
    # human rank is driven entirely by resolution + citation
    rows: list[CalibrationRow] = []
    for index in range(10):
        high = index < 5
        components = {
            "caption": 1.0,
            "artwork": 1.0,
            "resolution": 1.0 if high else 0.0,
            "area": 1.0,
            "vector": 0.0,
            "cited": 1.0 if high else 0.0,
            "crop_clean": 1.0,
        }
        rows.append(CalibrationRow(f"fig-{index}", components, human_rank=index + 1))
    baseline = QualityWeights(
        caption=0.5, vector=0.3, artwork=0.2, resolution=0.0, area=0.0, cited=0.0
    )
    report = calibrate(rows, baseline=baseline)
    assert report.improved
    # perfect separation with 5 ties gives rho = 0.87, which is the ceiling here
    assert report.best_spearman == pytest.approx(0.8704, abs=1e-3)
    assert report.best_spearman > report.baseline_spearman
    assert report.best_weights != baseline.normalised()
    # the components that actually carry the signal are identified
    assert report.component_spearman["resolution"] == pytest.approx(report.best_spearman)
    assert report.component_spearman["cited"] == pytest.approx(report.best_spearman)
    assert report.component_spearman["caption"] == pytest.approx(0.0)
    assert "[quality]" in report.toml_snippet()


def test_calibration_needs_enough_samples() -> None:
    with pytest.raises(ValueError, match="at least 5"):
        calibrate([CalibrationRow("a", {}, 1)] * 3)


def test_sheet_lists_rows_and_caption_only_assets(tmp_path: Path) -> None:
    manifests = [make_manifest(), make_manifest("pdf-abc12345/fig-2", chart_type=None)]
    sheet, contact = build_sheet(manifests, data_root=tmp_path, out_dir=tmp_path, limit=10)
    text = sheet.read_text()
    assert "pic" not in text
    assert "pdf-abc12345/fig-1" in text
    assert "human rank" in text
    assert contact is None  # no image files present


def test_sheet_builds_a_contact_sheet_when_images_exist(tmp_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    assets = tmp_path / "assets" / "pdf-abc12345" / "figures"
    assets.mkdir(parents=True)
    image = assets / "fig-1.png"
    figure = plt.figure(figsize=(2, 1.4))
    figure.text(0.1, 0.5, "figure")
    figure.savefig(image)
    plt.close(figure)

    manifest: ChartReproManifest = make_manifest()
    sheet, contact = build_sheet([manifest], data_root=tmp_path, out_dir=tmp_path, limit=5)
    assert "pdf-abc12345/fig-1" in sheet.read_text()
    assert contact is not None
    assert contact.is_file()


def test_design_tiers_follow_the_policy_thresholds() -> None:
    assert design_tier(0.9) == "gold"
    assert design_tier(0.55) == "gold"
    assert design_tier(0.5) == "dense"
    assert design_tier(0.45) == "dense"
    assert design_tier(0.3) == "reject"
    assert design_tier(None) is None
    assert design_tier(0.5, gold=0.6, dense=0.4) == "dense"
