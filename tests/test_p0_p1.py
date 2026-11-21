"""P0/P1: code assetization, KB refresh, schema search, filters, sheets, feedback."""

from __future__ import annotations

import json
import os
from pathlib import Path

from gaxis.kb.base import try_get_page
from gaxis.kb.ingest import KbIngestor
from gaxis.models.paper import CodeCandidate, ReproductionState
from gaxis.models.tools import SearchChartAssetsRequest
from gaxis.service import _kb_refresh, knowledge, search_chart_assets

from .manifest_factory import make_manifest


def _page(
    kb, slug: str, *, image: Path, chart: str = "bar", tier: str = "gold", code: str = ""
) -> None:
    kb.put_page(
        slug,
        "---\n"
        "type: analysis\n"
        f"title: {chart} figure for schema search\n"
        f"chart_type: {chart}\n"
        f"design_tier: {tier}\n"
        f"image_path: {image}\n"
        "reproduction_level: L2\n" + (f"code_path: {code}\n" if code else "") + "---\n\n"
        f"# {chart} figure\n\nbar chart of genotype and value\n",
    )


def _pattern(name: str, flipped: bool) -> Path:
    from PIL import Image, ImageDraw

    path = Path(os.environ["GAXIS_DATA_DIR"]) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(image)
    for index in range(0, 64, 8):
        if (index // 8) % 2 == int(flipped):
            draw.rectangle([index, 0, index + 7, 63], fill="black")
    image.save(path)
    return path


def test_schema_only_search_finds_shape_matches(fake_kb: Path) -> None:
    kb = knowledge()
    assert kb is not None
    image = _pattern("fig.png", False)
    _page(kb, "paper-kb:shape-1", image=image)
    data = Path(os.environ["GAXIS_DATA_DIR"]) / "table.csv"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("genotype,value\nWT,1\ndpsA,2\n", encoding="utf-8")
    result = search_chart_assets(SearchChartAssetsRequest(schema_path=str(data), query=""))
    assert result.assets
    assert result.assets[0].asset_id == "paper-kb:shape-1"
    assert result.assets[0].has_code is False


def test_filters_and_dedupe_and_sheet(fake_kb: Path) -> None:
    kb = knowledge()
    assert kb is not None
    first = _pattern("a.png", False)
    duplicate = _pattern("b.png", False)
    other = _pattern("c.png", True)
    _page(
        kb,
        "paper-kb:gold",
        image=first,
        tier="gold",
        code=str(Path(os.environ["GAXIS_DATA_DIR"]) / "code.py"),
    )
    _page(
        kb,
        "paper-kb:dup",
        image=duplicate,
        tier="gold",
        code=str(Path(os.environ["GAXIS_DATA_DIR"]) / "code.py"),
    )
    _page(kb, "paper-kb:dense", image=other, tier="dense")

    gold = search_chart_assets(
        SearchChartAssetsRequest(query="bar chart", design_tier="gold", dedupe=False, k=10)
    )
    assert {asset.asset_id for asset in gold.assets} == {"paper-kb:gold", "paper-kb:dup"}
    assert all(asset.has_code for asset in gold.assets)

    deduped = search_chart_assets(
        SearchChartAssetsRequest(query="bar chart", design_tier="gold", dedupe=True, k=10)
    )
    assert len(deduped.assets) == 1

    without_code = search_chart_assets(
        SearchChartAssetsRequest(query="bar chart", has_code=False, dedupe=False, k=10)
    )
    assert {asset.asset_id for asset in without_code.assets} == {"paper-kb:dense"}

    sheet = search_chart_assets(
        SearchChartAssetsRequest(query="bar chart", render_sheet=True, dedupe=False, k=10)
    )
    assert sheet.sheet_path is not None
    assert Path(sheet.sheet_path).is_file()


def test_kb_refresh_updates_a_graded_manifest(fake_kb: Path) -> None:
    kb = knowledge()
    assert kb is not None
    manifest = make_manifest(level="none")
    KbIngestor(kb, state_path=Path(os.environ["GAXIS_DATA_DIR"]) / "kb" / "state.json").ingest(
        [manifest]
    )
    manifest.reproduction = ReproductionState(
        level="L2", sandbox_run_status="success", visual_similarity=0.7
    )
    manifest.code_candidates = [
        CodeCandidate(
            code_path=str(Path(os.environ["GAXIS_DATA_DIR"]) / "code.py"),
            language="python",
            code_sha256="abc",
        )
    ]
    assert _kb_refresh(manifest) == "refreshed"
    page = try_get_page(kb, f"paper-kb:{manifest.manifest_id.replace('/', '-')}")
    assert page is not None
    assert page["frontmatter"]["reproduction_level"] == "L2"


def test_render_records_selection_feedback(fake_kb: Path, tmp_path: Path) -> None:
    from gaxis.models.tools import RenderRequest
    from gaxis.service import render

    data = Path(os.environ["GAXIS_DATA_DIR"]) / "expr.csv"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("g,v\nWT,1\nWT,2\nmut,3\nmut,4\n", encoding="utf-8")
    result = render(
        RenderRequest(
            data_path=str(data),
            preset="asm",
            formats=["pdf"],
            source_asset="paper-kb:gold",
            out_dir=str(tmp_path / "renders"),
        )
    )
    assert result.manifest.asset_ids == ["paper-kb:gold"]
    log = Path(os.environ["GAXIS_DATA_DIR"]) / "kb" / "selections.jsonl"
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["asset_id"] == "paper-kb:gold"
    assert entry["action"] == "render"
    assert entry["figure_id"] == result.figure_id
