"""KB pages and retrieval expose and use the usefulness score."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fitz")

from gaxis.config import load_config, settings
from gaxis.kb.gbrain import GbrainCLI
from gaxis.kb.ingest import KbIngestor
from gaxis.kb.search import search_assets
from gaxis.models.paper import DesignQuality, Usefulness

from .manifest_factory import make_manifest


def _seed(tmp_path: Path) -> GbrainCLI:
    kb = GbrainCLI(load_config().knowledge)
    strong = make_manifest(level="L1")
    strong.design = DesignQuality(
        model="vision:t", method="vision:t", aesthetic=0.8, visualization=0.8, score=0.8
    )
    strong.usefulness = Usefulness(score=0.9, notes=["venue: Nature Portfolio"])
    weak = make_manifest(
        "pdf-abc12345/fig-2", level="L1", caption="Figure 2. Bar chart.", citing=""
    )
    weak.design = DesignQuality(
        model="vision:t", method="vision:t", aesthetic=0.7, visualization=0.7, score=0.7
    )
    weak.usefulness = Usefulness(score=0.2, notes=["venue: unknown"])
    KbIngestor(kb, state_path=tmp_path / "data" / "kb" / "state.json").ingest([strong, weak])
    return kb


def test_page_carries_usefulness_and_search_uses_it(fake_kb: Path, tmp_path: Path) -> None:
    kb = _seed(tmp_path)
    page = kb.get_page("paper-kb:pdf-abc12345-fig-1")
    assert page is not None
    assert page["frontmatter"]["usefulness_score"] == pytest.approx(0.9)

    hits = search_assets(kb, "curve chart", k=2, types=["analysis"])
    assert hits
    assert hits[0].usefulness_score == pytest.approx(0.9)
    # weighted (design 0.7, usefulness 0.3): 0.7*0.8+0.3*0.9 > 0.7*0.7+0.3*0.2
    assert hits[0].asset_id == "pdf-abc12345/fig-1"


def test_design_weight_dominates_usefulness(fake_kb: Path, tmp_path: Path) -> None:
    kb = GbrainCLI(load_config().knowledge)
    design_led = make_manifest(level="L1")
    design_led.design = DesignQuality(
        model="v", method="v", aesthetic=0.9, visualization=0.9, score=0.9
    )
    design_led.usefulness = Usefulness(score=0.3)
    venue_led = make_manifest("pdf-abc12345/fig-2", level="L1", caption="Figure 2. Bar chart.")
    venue_led.design = DesignQuality(
        model="v", method="v", aesthetic=0.6, visualization=0.6, score=0.6
    )
    venue_led.usefulness = Usefulness(score=0.9)
    KbIngestor(kb, state_path=tmp_path / "data" / "kb" / "state.json").ingest(
        [design_led, venue_led]
    )
    hits = search_assets(kb, "figure", k=2, types=["analysis"])
    assert hits[0].asset_id == "pdf-abc12345/fig-1"
    assert settings().data_root  # settings usable without touching the real brain
