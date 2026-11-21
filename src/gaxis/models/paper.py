"""Paper-side models: what a parsed figure looks like before/after reproduction.

Follows plan §5.1 (ChartReproManifest) with the fields the M1 slice can actually
fill. Reproduction fields stay explicit and empty ("none"/"skipped") rather than
being omitted — M2 fills them, and a missing level is a fact, not a default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .spec import ChartType


class VisualGrammar(BaseModel):
    chart_type: ChartType | None = None
    color_scheme: list[str] = Field(default_factory=list)
    axis_style: str | None = None
    legend_layout: str | None = None
    subplot_layout: str | None = None
    notes: list[str] = Field(default_factory=list)


class CodeCandidate(BaseModel):
    code_path: str
    language: Literal["python", "r", "other"] = "python"
    entry_point: str | None = None
    dependency_hints: list[str] = Field(default_factory=list)
    packages: list[str] = Field(
        default_factory=list, description="pinned packages parsed from the repository"
    )
    input_schema_hints: dict[str, str] = Field(default_factory=dict)
    license: str | None = None
    pairing_confidence: float = 0.0
    code_sha256: str = Field(default="", description="hash of the stored code asset, when copied")
    generated: bool = Field(
        default=False, description="True when the script was written by the LLM, not the authors"
    )


class ReproductionState(BaseModel):
    level: Literal["L1", "L2", "L3", "none"] = "none"
    sandbox_run_status: Literal["success", "failed", "skipped"] = "skipped"
    visual_similarity: float | None = None
    failure_reason: str = ""
    environment_lock: str | None = None
    render_output: str | None = None
    data_source: Literal["none", "user", "repo", "synthetic"] = "none"
    method: Literal["none", "author_code", "llm_reconstruction", "llm_repair"] = "none"
    model: str | None = None
    attempts: int = 0


class DesignFeatures(BaseModel):
    """Measured design features; the score below must be explainable by these."""

    chart_like: bool = False
    photo_like: bool = False
    plate_like: bool = Field(
        default=False, description="montage of several complete figures, not one figure"
    )
    palette: list[str] = Field(default_factory=list)
    n_colours: int = 0
    colorblind_safe: bool | None = None
    ink_ratio: float = 0.0
    whitespace_ratio: float = 0.0
    margin_balance: float = 0.0
    min_font_pt: float | None = None
    caption_signals: list[str] = Field(default_factory=list)
    has_units: bool = False
    has_panels: bool = False
    has_uncertainty: bool = False


DesignTier = Literal["gold", "dense", "reject"]


class DesignQuality(BaseModel):
    """Design judgement.

    ``aesthetic`` is None unless a vision model (or a human) judged it: pixels and
    captions cannot measure taste, and pretending otherwise produced a score that
    rewarded technical parameters instead of good design. ``visualization`` is the
    objective half (labels, units, uncertainty, legibility, colour-blind safety).
    """

    model: str = "objective_v1"
    rubric: str = Field(default="v3.1", description="rubric version that produced the scores")
    method: str = Field(default="objective", description="objective | vision:<model> | human")
    aesthetic: float | None = Field(default=None, ge=0.0, le=1.0)
    visualization: float = Field(default=0.0, ge=0.0, le=1.0)
    score: float | None = Field(
        default=None, description="aesthetic+visualization; None until aesthetics is judged"
    )
    notes: list[str] = Field(default_factory=list)
    features: DesignFeatures = Field(default_factory=DesignFeatures)
    tier: DesignTier | None = Field(
        default=None, description="policy bucket from [design] thresholds; None = unjudged"
    )
    category: Literal["chart", "mixed", "schematic", "micrograph", "plate", "unknown"] | None = (
        Field(
            default=None,
            description="what kind of image this is; only chart/mixed are data figures",
        )
    )
    archetype: Literal["single", "plate"] = Field(
        default="single", description="single figure vs multi-figure plate (style reference)"
    )


class Usefulness(BaseModel):
    """Why this figure is worth reproducing (venue, evidence, panels, verification)."""

    score: float = Field(default=0.0, ge=0.0, le=1.0)
    components: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class FigureGeometry(BaseModel):
    """Where the figure came from, so a reviewer can check the extraction."""

    page: int
    bbox: tuple[float, float, float, float]
    pixel_width: int | None = None
    pixel_height: int | None = None
    is_vector: bool = False
    area_ratio: float = 0.0
    source: Literal["image_xobject", "vector_region"] = "image_xobject"
    crop_clean: float | None = Field(
        default=None, ge=0.0, le=1.0, description="pixel-level crop quality (0-1)"
    )


class ChartReproManifest(BaseModel):
    manifest_id: str
    paper_id: str
    paper_title: str | None = None
    doi: str | None = None
    source_url: str | None = None
    source_pdf: str | None = None
    figure_ref: str = ""
    chart_file: str = Field(
        default="", description="assets/... path; empty when artwork is missing"
    )
    caption: str = ""
    citing_paragraph: str = ""
    chart_quality_score: float = Field(
        default=0.0, description="extraction quality: caption/artwork/resolution/crop"
    )
    design: DesignQuality | None = Field(
        default=None, description="aesthetic + visualization quality (design_v1)"
    )
    usefulness: Usefulness | None = Field(
        default=None, description="venue/evidence/panel usefulness for reproduction"
    )
    geometry: FigureGeometry | None = None
    visual_grammar: VisualGrammar = Field(default_factory=VisualGrammar)
    code_candidates: list[CodeCandidate] = Field(default_factory=list)
    reproduction: ReproductionState = Field(default_factory=ReproductionState)
    asset_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def summary(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "figure_ref": self.figure_ref,
            "chart_type": self.visual_grammar.chart_type.value
            if self.visual_grammar.chart_type
            else None,
            "caption": self.caption[:160],
            "quality": self.chart_quality_score,
            "level": self.reproduction.level,
        }
