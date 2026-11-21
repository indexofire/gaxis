"""Persist a parsed paper: assets on disk, one ChartReproManifest per figure.

Layout under the data root:

    assets/<paper_id>/source.pdf
    assets/<paper_id>/figures/fig-<n>.<ext>
    manifests/<paper_id>__fig-<n>.json

Paths inside manifests are relative to the data root, so the tree can be moved or
backed up without rewriting every record.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..design import apply_plate_policy
from ..design_judge import DesignJudge, DesignJudgeError, HeuristicJudge
from ..models.paper import (
    ChartReproManifest,
    ReproductionState,
    Usefulness,
    VisualGrammar,
)
from ..parse.pdf import ExtractedFigure, ParsedPaper, parse_pdf
from ..quality import QualityWeights, apply_category_policy, design_tier, score_figure
from ..spec.brief import detect_chart_type
from ..usefulness import score_usefulness, usefulness_components, usefulness_notes


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    sha256: str
    source_path: Path
    page_count: int
    doi: str | None


def manifest_filename(manifest_id: str) -> str:
    return manifest_id.replace("/", "__") + ".json"


def paper_id_for(sha256: str) -> str:
    return f"pdf-{sha256[:8]}"


def quality_score(
    figure: ExtractedFigure,
    cited: bool,
    weights: QualityWeights | None = None,
) -> float:
    """Extraction fidelity: caption, artwork, resolution, area, vector source, citation."""
    geometry = figure.geometry
    return score_figure(
        caption=figure.caption,
        has_artwork=geometry is not None,
        largest_pixels=(
            max(geometry.pixel_width or 0, geometry.pixel_height or 0) if geometry else 0
        ),
        area_ratio=geometry.area_ratio if geometry else 0.0,
        is_vector=bool(geometry and geometry.is_vector),
        cited=cited,
        crop_clean=geometry.crop_clean if geometry else None,
        weights=weights or QualityWeights(),
    )


def build_manifests(
    parsed: ParsedPaper,
    *,
    paper_id: str,
    weights: QualityWeights | None = None,
    judge: DesignJudge | None = None,
    gold_score: float = 0.60,
    dense_score: float = 0.45,
    skip_plates: bool = True,
    allow_nonchart: bool = False,
) -> list[ChartReproManifest]:
    manifests: list[ChartReproManifest] = []
    for figure in parsed.figures:
        cited = parsed.citations.get(figure.number, [])
        chart_type = detect_chart_type(figure.caption)
        design = None
        if figure.image_bytes is not None:
            active = judge or HeuristicJudge()
            try:
                design = active.judge(
                    figure.image_bytes,
                    caption=figure.caption,
                    label_font_pt=figure.label_font_pt,
                )
            except DesignJudgeError as exc:
                design = HeuristicJudge().judge(
                    figure.image_bytes,
                    caption=figure.caption,
                    label_font_pt=figure.label_font_pt,
                )
                design.notes = [f"vision judge unavailable: {exc}", *design.notes]
            design = apply_plate_policy(design, skip_plates=skip_plates)
            design = apply_category_policy(design, allow_nonchart=allow_nonchart)
            design.tier = design_tier(  # type: ignore[assignment]
                design.score, gold=gold_score, dense=dense_score
            )
        notes = [f"caption found on page {figure.page}"]
        if figure.artwork_missing:
            notes.append(
                "artwork not present in this PDF (pre-proof or separate figure files); "
                "caption and citation recorded for retrieval, image must be added later"
            )
        elif figure.geometry is not None and figure.geometry.is_vector:
            notes.append("vector figure rendered from drawings at 300 dpi")
        if figure.pairing_note:
            notes.append(figure.pairing_note)
        manifests.append(
            ChartReproManifest(
                manifest_id=f"{paper_id}/fig-{figure.number}",
                paper_id=paper_id,
                paper_title=parsed.title,
                doi=parsed.doi,
                source_pdf=f"assets/{paper_id}/source.pdf",
                figure_ref=figure.figure_ref,
                chart_file=(
                    ""
                    if figure.artwork_missing
                    else f"assets/{paper_id}/figures/fig-{figure.number}.{figure.image_ext}"
                ),
                caption=figure.caption,
                citing_paragraph=" ".join(cited),
                chart_quality_score=quality_score(figure, bool(cited), weights),
                design=design,
                usefulness=Usefulness(),
                geometry=figure.geometry,
                visual_grammar=VisualGrammar(chart_type=chart_type, notes=notes),
                code_candidates=[],
                reproduction=ReproductionState(
                    level="none",
                    sandbox_run_status="skipped",
                    failure_reason="no paper code located yet (M1 repository parsing)",
                ),
                asset_ids=(
                    []
                    if figure.artwork_missing
                    else [f"assets/{paper_id}/figures/fig-{figure.number}.{figure.image_ext}"]
                ),
            )
        )
    for manifest in manifests:
        manifest.usefulness = Usefulness(
            score=score_usefulness(manifest),
            components=usefulness_components(manifest),
            notes=usefulness_notes(manifest),
        )
    return manifests


def ingest_pdf(
    path: Path,
    *,
    assets_root: Path,
    manifests_dir: Path,
    persist: bool = True,
    min_quality: float = 0.0,
    render_dpi: int = 300,
    weights: QualityWeights | None = None,
    judge: DesignJudge | None = None,
    gold_score: float = 0.60,
    dense_score: float = 0.45,
    skip_plates: bool = True,
    allow_nonchart: bool = False,
) -> tuple[PaperRecord, list[ChartReproManifest], ParsedPaper]:
    parsed = parse_pdf(path, render_dpi=render_dpi)
    paper_id = paper_id_for(parsed.sha256)
    record = PaperRecord(
        paper_id=paper_id,
        title=parsed.title,
        sha256=parsed.sha256,
        source_path=Path(path).expanduser().resolve(),
        page_count=parsed.page_count,
        doi=parsed.doi,
    )
    manifests = [
        m
        for m in build_manifests(parsed, paper_id=paper_id, weights=weights, judge=judge)
        if m.chart_quality_score >= min_quality
    ]
    if not persist:
        return record, manifests, parsed

    asset_dir = assets_root / paper_id
    figures_dir = asset_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(record.source_path, asset_dir / "source.pdf")
    by_number = {figure.number: figure for figure in parsed.figures}
    now = datetime.now(UTC)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    for manifest in manifests:
        number = int(manifest.manifest_id.rsplit("-", 1)[1])
        figure = by_number.get(number)
        if figure is None or figure.image_bytes is None or not manifest.chart_file:
            (manifests_dir / manifest_filename(manifest.manifest_id)).write_text(
                manifest.model_dump_json(indent=2), encoding="utf-8"
            )
            continue
        target = figures_dir / f"fig-{number}.{figure.image_ext}"
        target.write_bytes(figure.image_bytes)
        manifest.updated_at = now
        manifest.created_at = now
        (manifests_dir / manifest_filename(manifest.manifest_id)).write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
    return record, manifests, parsed


def load_manifest(manifest_id: str, manifests_dir: Path) -> ChartReproManifest | None:
    path = manifests_dir / manifest_filename(manifest_id)
    if not path.is_file():
        return None
    return ChartReproManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
