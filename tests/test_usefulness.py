"""Usefulness: venue/evidence/panel signals that decide whether a figure is reused."""

from __future__ import annotations

import pytest

pytest.importorskip("fitz")

from gaxis.models.paper import DesignQuality
from gaxis.usefulness import (
    UsefulnessWeights,
    journal_tier,
    panel_count,
    score_usefulness,
    usefulness_components,
)

from .manifest_factory import make_manifest


def test_journal_tiers_follow_the_microbiology_landscape() -> None:
    assert journal_tier("10.1038/s41564-020-00783-x")[0] == 1.0
    assert journal_tier("10.1128/mbio.00001-24")[0] == 0.92
    assert journal_tier("10.1371/journal.pone.0000217")[0] == 0.82
    assert journal_tier("10.1101/2024.01.01.000001")[0] == 0.72
    # venue range is deliberately narrow: 0.72-1.0, not 0.2-1.0
    assert journal_tier(None)[0] == 0.85


def test_panel_count_reads_ranges_and_markers() -> None:
    assert panel_count("Fig. 1. Panels a-d show ...") == 4
    assert panel_count("Fig. 2. (a) growth, (b) survival, (c) heatmap") == 3
    assert panel_count("no panels mentioned") == 1


def test_verified_journal_figure_scores_above_a_preprint() -> None:
    strong = make_manifest()
    strong.doi = "10.1038/s41564-020-00783-x"
    strong.caption = "Fig. 1. Panels a-d. Bars are mean ± s.d. (n = 12) over 24 h."
    strong.design = DesignQuality(
        model="vision:test", method="vision:test", aesthetic=0.8, visualization=0.8, score=0.8
    )
    strong.design.features.caption_signals = ["uncertainty", "units", "panels", "sample_size"]
    strong.reproduction.level = "L1"

    weak = make_manifest()
    weak.doi = "10.1101/2024.01.01.000001"
    weak.caption = "Fig 1."
    weak.design = DesignQuality(model="vision:test", method="vision:test", score=0.5)

    assert score_usefulness(strong) > score_usefulness(weak)
    assert usefulness_components(strong)["journal"] == 1.0
    assert usefulness_components(strong)["verification"] == 1.0


def test_venue_alone_cannot_dominate_a_weak_figure() -> None:
    strong_venue = make_manifest()
    strong_venue.doi = "10.1038/s41564-020-00783-x"
    strong_venue.design = DesignQuality(model="vision:test", method="vision:test", score=0.4)
    weak_venue = make_manifest()
    weak_venue.doi = "10.1371/journal.pone.0000217"
    weak_venue.design = DesignQuality(model="vision:test", method="vision:test", score=0.4)
    assert 0.0 < score_usefulness(strong_venue) - score_usefulness(weak_venue) < 0.15


def test_weights_are_explainable_and_normalised() -> None:
    manifest = make_manifest()
    manifest.design = DesignQuality(model="vision:test", method="vision:test", score=0.7)
    base = score_usefulness(manifest)
    doubled = score_usefulness(
        manifest,
        UsefulnessWeights(
            journal=0.40, statistics=0.50, verification=0.50, panels=0.40, caption=0.20
        ),
    )
    assert base == pytest.approx(doubled)
    assert 0.0 <= base <= 1.0
