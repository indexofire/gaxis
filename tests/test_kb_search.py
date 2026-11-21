"""Retrieval: chunk hits -> one asset per page, filtered and ranked."""

from __future__ import annotations

from pathlib import Path

from gaxis.config import load_config
from gaxis.kb.gbrain import GbrainCLI
from gaxis.kb.ingest import KbIngestor
from gaxis.kb.search import search_assets
from gaxis.models.paper import DesignQuality
from gaxis.models.spec import ChartType
from gaxis.models.tools import SearchChartAssetsRequest
from gaxis.service import search_chart_assets

from .manifest_factory import make_manifest


def _design(score: float, tier: str) -> DesignQuality:
    return DesignQuality(
        model="vision:test",
        method="vision:test",
        aesthetic=score,
        visualization=score,
        score=score,
        tier=tier,  # type: ignore[arg-type]
    )


def _seed(tmp_path: Path) -> GbrainCLI:
    kb = GbrainCLI(load_config().knowledge)
    first = make_manifest(level="L1", chart_type=ChartType.line)
    first.design = _design(0.8, "gold")
    second = make_manifest(
        "pdf-abc12345/fig-2",
        level="L3",
        chart_type=ChartType.bar,
        caption="Figure 2. Bar chart of expression across genotypes.",
        citing="Expression is shown in Fig. 2.",
        visual_similarity=None,
    )
    second.design = _design(0.3, "reject")
    KbIngestor(kb, state_path=tmp_path / "data" / "kb" / "state.json").ingest(
        [
            first,
            second,
        ]
    )
    return kb


def test_search_returns_assets_ranked_by_level(fake_kb: Path, tmp_path: Path) -> None:
    kb = _seed(tmp_path)
    hits = search_assets(kb, "rarefaction richness", k=5, types=["analysis"])
    assert hits
    assert hits[0].asset_id == "pdf-abc12345/fig-1"
    assert hits[0].reproduction_level == "L1"
    assert hits[0].chart_type is ChartType.line
    assert hits[0].design_score is not None
    assert hits[0].design_tier in {"gold", "dense", "reject"}


def test_min_level_filters_out_low_grades(fake_kb: Path, tmp_path: Path) -> None:
    kb = _seed(tmp_path)
    hits = search_assets(kb, "expression genotypes bar", k=5, min_level="L2")
    assert all(hit.reproduction_level in {"L1", "L2"} for hit in hits)


def test_chart_type_filter_is_pushed_into_the_query(fake_kb: Path, tmp_path: Path) -> None:
    kb = _seed(tmp_path)
    hits = search_assets(kb, "expression genotypes", k=5, chart_type="bar")
    assert hits
    assert {hit.chart_type for hit in hits} == {ChartType.bar}


def test_service_marks_degraded_only_when_unavailable(fake_kb: Path, tmp_path: Path) -> None:
    _seed(tmp_path)
    ok = search_chart_assets(SearchChartAssetsRequest(query="rarefaction"))
    assert ok.degraded is False
    assert ok.assets
    empty = search_chart_assets(SearchChartAssetsRequest(query="mass spectrometry proteomics"))
    assert empty.degraded is False
    assert empty.assets == []
    assert "no matching" in empty.message


def test_service_degrades_when_gbrain_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAXIS_GBRAIN_BIN", str(tmp_path / "missing-gbrain"))
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path / "data"))
    result = search_chart_assets(SearchChartAssetsRequest(query="rarefaction"))
    assert result.degraded is True
    assert result.assets == []
    assert result.message


def test_strict_chart_filter_falls_back_to_textual_matches(fake_kb: Path, tmp_path: Path) -> None:
    _seed(tmp_path)
    result = search_chart_assets(
        SearchChartAssetsRequest(query="rarefaction richness", chart_type=ChartType.bar)
    )
    assert result.assets, "a strict filter must not hide a textual match"
    assert "showing textual matches instead" in result.message


def test_image_query_ranks_by_perceptual_similarity(fake_kb: Path, tmp_path: Path) -> None:
    from PIL import Image, ImageDraw

    def pattern(name: str, flipped: bool) -> Path:
        path = tmp_path / name
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        for index in range(0, 64, 8):
            if (index // 8) % 2 == int(flipped):
                draw.rectangle([index, 0, index + 7, 63], fill="black")
        image.save(path)
        return path

    query = pattern("query.png", flipped=False)
    same = pattern("same.png", flipped=False)
    other = pattern("other.png", flipped=True)

    kb = GbrainCLI(load_config().knowledge)
    for slug, image_path, title in (
        ("paper-kb:same", same, "bar chart striped pattern"),
        ("paper-kb:other", other, "bar chart striped pattern inverted"),
    ):
        kb.put_page(
            slug,
            "---\n"
            "type: analysis\n"
            f"title: {title}\n"
            f"image_path: {image_path}\n"
            "reproduction_level: L3\n"
            "---\n\n"
            f"# {title}\n\nbar chart striped pattern\n",
        )
    hits = search_assets(
        kb, "bar chart", k=2, types=["analysis"], data_root=tmp_path, query_image=query
    )
    assert [hit.asset_id for hit in hits] == ["paper-kb:same", "paper-kb:other"]
    assert hits[0].image_similarity == 1.0
    assert hits[1].image_similarity is not None
    assert hits[1].image_similarity < 1.0
