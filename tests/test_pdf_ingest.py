"""M1 vertical slice: local PDF -> figures -> ChartReproManifest -> get_chart_manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fitz")

from gaxis.acquire.paper import load_manifest
from gaxis.models.tools import (
    GetChartManifestRequest,
    IngestPaperRequest,
)
from gaxis.parse.pdf import parse_pdf
from gaxis.service import get_chart_manifest, ingest_paper

from .pdf_fixture import (
    build_caption_only_pdf,
    build_sample_pdf,
    build_split_layout_pdf,
)


@pytest.fixture(scope="module")
def sample_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("paper")
    path = directory / "sample-paper.pdf"
    return build_sample_pdf(path)


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    monkeypatch.setenv("GAXIS_DATA_DIR", str(root))
    return root


def test_parse_finds_figure_caption_and_citing_paragraph(sample_pdf: Path) -> None:
    parsed = parse_pdf(sample_pdf)
    assert parsed.page_count == 2
    assert len(parsed.figures) == 1, [f.caption for f in parsed.figures]
    figure = parsed.figures[0]
    assert figure.figure_ref == "Fig. 1"
    assert "Grouped bar chart" in figure.caption
    assert figure.geometry.page == 1
    assert figure.image_bytes is not None
    assert len(figure.image_bytes) > 1000
    cited = parsed.citations[1]
    assert any("rpoS expression increased" in paragraph for paragraph in cited)
    # the "Fig. 2" mention must not be attributed to figure 1
    assert all("companion paper" not in paragraph for paragraph in cited)
    assert parsed.title.startswith("Nitrogen stress")


def test_kb_first_parses_without_writing_anything(sample_pdf: Path, data_root: Path) -> None:
    result = ingest_paper(IngestPaperRequest(source=str(sample_pdf), mode="kb_first"))
    assert result.mode == "kb_first"
    assert result.charts_found == 1
    assert result.figure_briefs[0].figure_ref == "Fig. 1"
    assert result.figure_briefs[0].chart_type_guess is not None
    assert result.manifest_ids == []
    assert result.not_implemented is False
    assert not data_root.exists() or not list((data_root / "manifests").glob("*.json"))


def test_full_mode_persists_assets_and_manifests(sample_pdf: Path, data_root: Path) -> None:
    result = ingest_paper(IngestPaperRequest(source=str(sample_pdf), mode="full"))
    assert result.mode == "full"
    assert result.paper_id.startswith("pdf-")
    assert len(result.manifest_ids) == 1

    manifest_id = result.manifest_ids[0]
    stored = load_manifest(manifest_id, data_root / "manifests")
    assert stored is not None
    assert stored.paper_id == result.paper_id
    assert stored.chart_quality_score >= 0.5
    assert stored.reproduction.level == "none"

    chart = data_root / stored.chart_file
    assert chart.is_file()
    assert chart.stat().st_size > 1000
    assert (data_root / stored.source_pdf).is_file()

    fetched = get_chart_manifest(GetChartManifestRequest(manifest_id=manifest_id))
    assert fetched.found is True
    assert fetched.manifest is not None
    assert fetched.manifest["geometry"]["page"] == 1


def test_unknown_manifest_is_reported_not_raised(data_root: Path) -> None:
    fetched = get_chart_manifest(GetChartManifestRequest(manifest_id="pdf-deadbeef/fig-9"))
    assert fetched.found is False
    assert "ingest_paper" in fetched.message


def test_caption_without_artwork_is_not_fabricated(tmp_path: Path, data_root: Path) -> None:
    pdf = build_caption_only_pdf(tmp_path / "legends-only.pdf")
    result = ingest_paper(IngestPaperRequest(source=str(pdf), mode="full"))
    assert result.charts_found == 1
    stored = load_manifest(result.manifest_ids[0], data_root / "manifests")
    assert stored is not None
    assert stored.chart_file == ""
    assert stored.asset_ids == []
    assert stored.geometry is None
    assert any("artwork not present" in note for note in stored.visual_grammar.notes)
    assert stored.chart_quality_score < 0.6


def test_preproof_artwork_is_paired_across_pages(tmp_path: Path, data_root: Path) -> None:
    pdf = build_split_layout_pdf(tmp_path / "split-layout.pdf")
    result = ingest_paper(IngestPaperRequest(source=str(pdf), mode="full"))
    stored = load_manifest(result.manifest_ids[0], data_root / "manifests")
    assert stored is not None
    assert stored.chart_file.endswith(".png")
    assert stored.geometry is not None
    assert stored.geometry.page == 2
    assert any("paired across pages" in note for note in stored.visual_grammar.notes)
    assert (data_root / stored.chart_file).is_file()


def test_manifest_json_is_stable_and_relative(sample_pdf: Path, data_root: Path) -> None:
    result = ingest_paper(IngestPaperRequest(source=str(sample_pdf), mode="full"))
    path = next((data_root / "manifests").glob("*.json"))
    payload = json.loads(path.read_text())
    assert payload["manifest_id"] == result.manifest_ids[0]
    assert not Path(payload["chart_file"]).is_absolute()
    assert payload["caption"].startswith("Fig. 1.")
