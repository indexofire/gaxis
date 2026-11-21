"""Test helper: build ChartReproManifest objects without touching a PDF."""

from __future__ import annotations

from gaxis.models.paper import (
    ChartReproManifest,
    CodeCandidate,
    FigureGeometry,
    ReproductionState,
    VisualGrammar,
)
from gaxis.models.spec import ChartType


def make_manifest(
    manifest_id: str = "pdf-abc12345/fig-1",
    *,
    chart_type: ChartType | None = ChartType.line,
    level: str = "L1",
    visual_similarity: float | None = 0.91,
    caption: str = "Figure 1. Rarefaction curves of ASVs against sequencing depth.",
    citing: str = "As shown in Fig. 1, richness plateaued at 20,000 reads.",
    image: str = "assets/pdf-abc12345/figures/fig-1.png",
    code: bool = True,
    quality: float = 0.85,
) -> ChartReproManifest:
    return ChartReproManifest(
        manifest_id=manifest_id,
        paper_id="pdf-abc12345",
        paper_title="Nitrogen stress reshapes the transcriptome",
        doi="10.1099/mgen.0.000001",
        source_pdf="assets/pdf-abc12345/source.pdf",
        figure_ref="Fig. 1",
        chart_file=image,
        caption=caption,
        citing_paragraph=citing,
        chart_quality_score=quality,
        geometry=FigureGeometry(
            page=4,
            bbox=(70, 200, 520, 500),
            pixel_width=1400,
            pixel_height=900,
            area_ratio=0.4,
            is_vector=True,
            crop_clean=1.0,
        ),
        visual_grammar=VisualGrammar(chart_type=chart_type, notes=["legend outside right"]),
        code_candidates=[CodeCandidate(code_path="assets/pdf-abc12345/figure.py")] if code else [],
        reproduction=ReproductionState(
            level=level,  # type: ignore[arg-type]
            sandbox_run_status="success" if level != "none" else "skipped",
            visual_similarity=visual_similarity,
            failure_reason="" if level == "L1" else "structurally similar",
        ),
    )
