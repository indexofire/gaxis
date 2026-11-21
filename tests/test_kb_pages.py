"""Manifest -> gbrain page: filterable frontmatter and searchable body."""

from __future__ import annotations

from gaxis.kb.pages import build_page, page_slug
from gaxis.models.spec import ChartType

from .manifest_factory import make_manifest


def test_slug_is_source_scoped_and_filename_safe() -> None:
    assert page_slug("paper-kb", "pdf-abc12345/fig-3") == "paper-kb:pdf-abc12345-fig-3"


def test_frontmatter_carries_the_filterable_facts() -> None:
    slug, markdown = build_page(make_manifest(), source="paper-kb")
    assert slug == "paper-kb:pdf-abc12345-fig-1"
    front = markdown.split("---")[1]
    assert "type: analysis" in front
    assert "asset_id: pdf-abc12345/fig-1" in front
    assert "chart_type: line" in front
    assert "reproduction_level: L1" in front
    assert "image_path: assets/pdf-abc12345/figures/fig-1.png" in front
    assert "doi: 10.1099/mgen.0.000001" in front
    assert "visual_similarity: 0.91" in front


def test_body_is_what_a_human_or_llm_would_search() -> None:
    _, markdown = build_page(make_manifest(), source="paper-kb")
    assert "Rarefaction curves of ASVs" in markdown
    assert "**Caption.**" in markdown
    assert "**Citing paragraph.**" in markdown
    assert "richness plateaued" in markdown
    assert "also known as: line chart" in markdown
    assert "折线图" in markdown  # bilingual synonyms for Chinese briefs
    assert "level L1" in markdown
    assert "**Image.**" in markdown


def test_caption_only_assets_say_so() -> None:
    _, markdown = build_page(make_manifest(image=""), source="paper-kb")
    assert "Not present in the source PDF" in markdown


def test_missing_chart_type_does_not_invent_synonyms() -> None:
    _, markdown = build_page(make_manifest(chart_type=None), source="paper-kb")
    assert "also known as" not in markdown
    assert "chart type" not in markdown


def test_page_is_deterministic() -> None:
    manifest = make_manifest(chart_type=ChartType.heatmap)
    first = build_page(manifest, source="paper-kb")
    second = build_page(manifest, source="paper-kb")
    assert first == second
