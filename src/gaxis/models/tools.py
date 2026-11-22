"""MCP tool contract v2.3 — frozen surface between the kernel and every host.

Seven tools, one core. Hosts (bacmap, DSH, Pi, Hermes, CLI) only translate; the
kernel never learns about a host SDK (ADR-05). Every tool declares its data
class, side effects and network need so a host such as bacmap can gate calls by
its own profile ceiling *before* execution, instead of after a leak.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .. import __version__
from .composition import CompositionManifest
from .lint import LintReport
from .manifest import FigureManifest, OutputFile
from .schema import DataSchema
from .spec import ChartSpec, ChartType

Backend = Literal["python", "r"]


class DataClass(StrEnum):
    """Mirrors bacmap's classification so a host can map ceilings 1:1."""

    d1_public = "D1"
    d2_internal = "D2"
    d3_sensitive = "D3"
    d4_local_only = "D4"


class DescribeDataRequest(BaseModel):
    data_path: str = Field(description="Absolute path to a CSV/TSV table (one observation per row)")


class DescribeDataResult(BaseModel):
    data_schema: DataSchema
    suggested_spec: ChartSpec
    summary: str


class RenderRequest(BaseModel):
    """Everything a caller needs to go from a table to a journal figure."""

    data_path: str
    chart_type: ChartType | None = None
    x: str | None = None
    y: str | None = None
    hue: str | None = None
    yerr: str | None = None
    weight: str | None = None
    title: str | None = None
    xlabel: str | None = None
    ylabel: str | None = None
    preset: str = "default"
    palette: str | None = None
    backend: Backend = "python"
    width_mm: float | None = None
    height_mm: float | None = None
    dpi: int = 600
    formats: list[str] = Field(default_factory=lambda: ["pdf", "png"])
    annotate_values: bool = False
    out_dir: str | None = None
    source_asset: str | None = Field(
        default=None, description="KB asset this figure follows (selection feedback)"
    )

    def to_spec(self) -> ChartSpec:
        return ChartSpec(
            chart_type=self.chart_type or ChartType.bar,
            x=self.x,
            y=self.y,
            hue=self.hue,
            yerr=self.yerr,
            weight=self.weight,
            title=self.title,
            xlabel=self.xlabel,
            ylabel=self.ylabel,
            preset=self.preset,
            palette=self.palette,
            backend=self.backend,
            width_mm=self.width_mm,
            height_mm=self.height_mm,
            dpi=self.dpi,
            formats=self.formats,
            annotate_values=self.annotate_values,
        )


class RenderResult(BaseModel):
    figure_id: str
    manifest_path: str
    manifest: FigureManifest
    code_path: str
    outputs: list[OutputFile]
    lint: LintReport
    exec_stdout: str = ""
    exec_stderr: str = ""
    duration_s: float = 0.0


class ColumnRole(BaseModel):
    """What the plan needs from the user's table, in role terms, not column names."""

    role: Literal["x", "y", "hue", "yerr", "facet"]
    kind: Literal["numeric", "categorical"]
    hint: str


class ChartPlan(BaseModel):
    """A data-free proposal produced from a natural-language brief.

    This is what makes service flow 1 possible: converge on the figure *before*
    the user has a tidy table, then render once the data arrives.
    """

    brief: str
    spec: ChartSpec
    required_columns: list[ColumnRole] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    candidate_asset_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PlanChartRequest(BaseModel):
    brief: str = Field(description="Natural language: chart type, style, target journal, anything")
    preset: str | None = None
    backend: Backend | None = None
    k: int = Field(default=5, ge=1, le=50)


class PlanChartResult(BaseModel):
    plan: ChartPlan
    matches: list[ChartAssetSummary] = Field(default_factory=list)
    degraded: bool = False
    message: str = ""
    # Whether the host must confirm with the user before rendering. Computed from the
    # configured policy (`[confirmation]` in gaxis.toml) so hosts do not re-invent it.
    requires_confirmation: bool = True
    confirmation_threshold: float = 0.6
    confirmation_mode: Literal["auto", "always", "never"] = "auto"


class FigureBrief(BaseModel):
    """One figure of a paper, as far as we understand it before deep parsing."""

    figure_ref: str = Field(description='e.g. "Fig. 3" or "Figure 3A"')
    caption: str = ""
    chart_type_guess: ChartType | None = None
    kb_match_asset_ids: list[str] = Field(default_factory=list)
    needs_deep_parse: bool = True


class IngestPaperRequest(BaseModel):
    """Service flow 2 entry point: a paper in, its figures and code out.

    ``mode="kb_first"`` is the default on purpose: show the user what the knowledge
    base already has before paying for paper parsing and sandbox reproduction.
    """

    source: str = Field(description="PDF path, DOI, arXiv id, PubMed/PMC id, or URL")
    mode: Literal["kb_first", "full"] | None = Field(
        default=None, description="Defaults to [ingest] default_mode (kb_first)"
    )
    min_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    reproduce: bool | None = Field(
        default=None, description="Run the sandbox pipeline; defaults to True only for mode=full"
    )
    timeout_s: float = Field(default=900, gt=0, le=7200)
    with_code: bool | None = Field(
        default=None, description="Look for the paper's repository; defaults to config"
    )


class IngestPaperResult(BaseModel):
    source: str = ""
    source_kind: Literal["pdf", "doi", "arxiv", "pmid", "pmcid", "url", "unknown"] = "unknown"
    normalised_id: str = ""
    mode: Literal["kb_first", "full"] = "kb_first"
    needs_network: bool = False

    paper_id: str = ""
    title: str | None = None
    doi: str | None = None
    pdf_url: str | None = None
    repository_urls: list[str] = Field(default_factory=list)
    code_candidate_count: int = 0
    figure_briefs: list[FigureBrief] = Field(default_factory=list)
    matches: list[ChartAssetSummary] = Field(default_factory=list)
    manifest_ids: list[str] = Field(default_factory=list)
    charts_found: int = 0
    reproduced: dict[str, int] = Field(default_factory=dict)
    deep_parse_suggested: bool = False
    not_implemented: bool = True
    message: str = ""


class ChartAssetSummary(BaseModel):
    asset_id: str
    paper_title: str | None = None
    doi: str | None = None
    chart_type: ChartType | None = None
    reproduction_level: Literal["L1", "L2", "L3"] | None = None
    visual_similarity: float | None = None
    preset_hint: str | None = None
    thumb_path: str | None = None
    design_score: float | None = Field(
        default=None, description="aesthetic+visualization score (null until judged)"
    )
    design_tier: Literal["gold", "dense", "reject"] | None = Field(
        default=None, description="policy bucket from [design] thresholds"
    )
    usefulness_score: float | None = Field(
        default=None, description="venue/evidence/panel usefulness (0-1)"
    )
    image_similarity: float | None = Field(
        default=None, description="perceptual (dHash) similarity to the query image, 0-1"
    )
    has_code: bool = Field(default=False, description="a code candidate is recorded")
    reproduction_method: str | None = Field(
        default=None, description="author_code | llm_reconstruction | llm_repair | none"
    )


class SearchChartAssetsRequest(BaseModel):
    query: str = Field(default="", description="free-text intent; may be empty with schema_path")
    query_image_path: str | None = Field(
        default=None, description="optional figure image; adds perceptual similarity ranking"
    )
    schema_path: str | None = Field(
        default=None, description="profile this table and search for figures that fit its shape"
    )
    k: int = Field(default=5, ge=1, le=50)
    chart_type: ChartType | None = None
    min_reproduction_level: Literal["L1", "L2", "L3"] | None = None
    preset: str | None = None
    design_tier: Literal["gold", "dense", "reject"] | None = None
    has_code: bool | None = Field(
        default=None, description="only assets with a recorded code candidate"
    )
    dedupe: bool = Field(default=True, description="collapse perceptually identical figures")
    render_sheet: bool = Field(
        default=False, description="write a contact sheet of the candidates and return its path"
    )


class SearchChartAssetsResult(BaseModel):
    assets: list[ChartAssetSummary] = Field(default_factory=list)
    total: int = 0
    degraded: bool = False
    message: str = ""
    sheet_path: str | None = Field(
        default=None, description="contact sheet written when render_sheet=true"
    )


class GetChartManifestRequest(BaseModel):
    manifest_id: str


class GetChartManifestResult(BaseModel):
    manifest_id: str
    found: bool
    manifest: dict[str, Any] | None = None
    message: str = ""


class ReproduceChartCodeRequest(BaseModel):
    manifest_id: str
    code_path: str | None = Field(
        default=None,
        description="Path to the python script to run; defaults to the manifest's best candidate",
    )
    data_path: str | None = Field(
        default=None, description="Optional input data, mounted read-only at /data"
    )
    timeout_s: float = Field(default=300, gt=0, le=3600)
    allow_network: bool = False
    engine: Literal["podman", "local"] | None = Field(
        default=None, description="Override the configured sandbox backend"
    )


class ReproduceChartCodeResult(BaseModel):
    manifest_id: str
    level: Literal["L1", "L2", "L3", "none"] = "none"
    run_status: Literal["success", "failed", "skipped"] = "skipped"
    visual_similarity: float | None = None
    failure_reason: str = ""
    outputs: list[OutputFile] = Field(default_factory=list)
    lint: LintReport = Field(default_factory=LintReport)
    engine: Literal["podman", "local", "none"] = "none"
    language: Literal["python", "r"] = "python"
    code_path: str = ""
    code_sha256: str = ""
    sandbox_report: dict[str, Any] = Field(default_factory=dict)
    similarity_detail: dict[str, float] = Field(default_factory=dict)
    manifest_path: str = ""
    not_implemented: bool = False


class AdaptChartCodeRequest(BaseModel):
    data_path: str
    query: str | None = None
    asset_id: str | None = None
    preset: str = "default"
    backend: Backend = "python"
    formats: list[str] = Field(default_factory=lambda: ["pdf", "png"])
    dpi: int = 600
    dry_run: bool = False


class AdaptChartCodeResult(BaseModel):
    figure_id: str = ""
    code_path: str = ""
    outputs: list[OutputFile] = Field(default_factory=list)
    lint: LintReport = Field(default_factory=LintReport)
    source: Literal["kb_asset", "builtin_templates"] = "builtin_templates"
    asset_ids: list[str] = Field(default_factory=list)
    fallback_reason: str = ""
    not_implemented: bool = True


class ComposePanelsRequest(BaseModel):
    """`compose_panels`: arrange already-rendered figures on one publication page."""

    panel_ids: list[str] = Field(min_length=2, max_length=8)
    preset: str = "default"
    layout: str | None = Field(default=None, pattern=r"^\d+x\d+$")
    width_mm: float | None = None
    height_mm: float | None = None
    labels: bool = True
    uniform: bool = False
    out_dir: str | None = None


class HealthStatus(BaseModel):
    ok: bool = True
    version: str = __version__
    data_root: str
    python_backend: bool = False
    r_backend: bool = False
    presets: list[str] = Field(default_factory=list)
    stages: dict[str, str] = Field(default_factory=dict)
    message: str = ""


class NotImplementedResult(BaseModel):
    status: Literal["not_implemented"] = "not_implemented"
    tool: str
    planned_milestone: str
    message: str


class ToolSpec(BaseModel):
    """Machine-readable description of one MCP tool (used by hosts for gating)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    summary: str
    data_class: DataClass
    side_effects: list[str]
    needs_network: bool
    cost: Literal["ms", "s", "min", "10min+"]
    implemented: bool
    milestone: str
    input_model: str
    output_model: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


def _spec(**kwargs: Any) -> ToolSpec:
    """Build a ToolSpec, exporting JSON Schemas from the pydantic models."""
    return ToolSpec(**kwargs)


class _EmptyRequest(BaseModel):
    """health takes no arguments."""


class _ContractModel(BaseModel):
    """Marker so the tool-spec table below can be typed without Any."""

    @classmethod
    def export_schema(cls) -> dict[str, Any]:
        return cls.model_json_schema()


_INPUT_MODELS: dict[str, type[BaseModel]] = {
    "describe_data_schema": DescribeDataRequest,
    "render_chart_from_data": RenderRequest,
    "search_chart_assets": SearchChartAssetsRequest,
    "get_chart_manifest": GetChartManifestRequest,
    "reproduce_chart_code": ReproduceChartCodeRequest,
    "adapt_chart_code": AdaptChartCodeRequest,
    "compose_panels": ComposePanelsRequest,
    "plan_chart_from_brief": PlanChartRequest,
    "ingest_paper": IngestPaperRequest,
    "health": _EmptyRequest,
}
_OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "describe_data_schema": DescribeDataResult,
    "render_chart_from_data": RenderResult,
    "search_chart_assets": SearchChartAssetsResult,
    "get_chart_manifest": GetChartManifestResult,
    "reproduce_chart_code": ReproduceChartCodeResult,
    "adapt_chart_code": AdaptChartCodeResult,
    "compose_panels": CompositionManifest,
    "plan_chart_from_brief": PlanChartResult,
    "ingest_paper": IngestPaperResult,
    "health": HealthStatus,
}
_ROWS = [
    (
        "describe_data_schema",
        "Profile a tidy table: column kinds, cardinality, units, suggested chart.",
        DataClass.d3_sensitive,
        [],
        False,
        "ms",
        True,
        "M0",
    ),
    (
        "render_chart_from_data",
        "Render a publication-grade figure from user data and return the code that made it.",
        DataClass.d3_sensitive,
        ["reads data file", "writes data/renders", "executes sandboxed script"],
        False,
        "s",
        True,
        "M0",
    ),
    (
        "search_chart_assets",
        "Search the paper chart knowledge base (visual + caption + code semantics).",
        DataClass.d1_public,
        [],
        False,
        "s",
        True,
        "M3",
    ),
    (
        "get_chart_manifest",
        "Fetch a ChartReproManifest by id, including code candidates and reproduction level.",
        DataClass.d1_public,
        [],
        False,
        "ms",
        True,
        "M1",
    ),
    (
        "reproduce_chart_code",
        "Run a paper figure's code in the sandbox, compare renderings, assign L1/L2/L3.",
        DataClass.d1_public,
        ["writes data/repro", "executes sandboxed script"],
        False,
        "min",
        True,
        "M2",
    ),
    (
        "adapt_chart_code",
        "Retrieve a KB template, adapt it to local data, trial-run it, return figure + code.",
        DataClass.d3_sensitive,
        ["reads data file", "writes data/renders", "executes sandboxed script"],
        False,
        "s",
        True,
        "M4 KB templates (builtin fallback reported)",
    ),
    (
        "compose_panels",
        "Arrange rendered panels into one vector page (A/B/C labels, composition manifest).",
        DataClass.d3_sensitive,
        ["reads data/renders", "writes composition PDF/PNG/JSON"],
        False,
        "s",
        True,
        "M4",
    ),
    (
        "plan_chart_from_brief",
        "Turn a natural-language figure request into a data-free plan: spec, required "
        "columns, style notes, open questions, matching knowledge-base cases.",
        DataClass.d1_public,
        [],
        False,
        "ms",
        True,
        "M0 (heuristics) / M3 (KB cases)",
    ),
    (
        "ingest_paper",
        "Ingest one paper on demand: extract figures, captions, citing paragraphs and code, "
        "then reproduce them into the knowledge base.",
        DataClass.d1_public,
        ["writes data/assets", "writes data/manifests", "executes sandboxed script"],
        True,
        "10min+",
        True,
        "M1 PDF ingest (DOI resolution M1, reproduction M2)",
    ),
    (
        "health",
        "Read-only probe: no side effects, safe to poll for liveness and clock-skew checks.",
        DataClass.d1_public,
        [],
        False,
        "ms",
        True,
        "M0",
    ),
]

TOOL_SPECS: list[ToolSpec] = [
    _spec(
        name=name,
        summary=summary,
        data_class=data_class,
        side_effects=effects,
        needs_network=network,
        cost=cost,
        implemented=implemented,
        milestone=milestone,
        input_model=_INPUT_MODELS[name].__name__,
        output_model=_OUTPUT_MODELS[name].__name__,
        input_schema=_INPUT_MODELS[name].model_json_schema(),
        output_schema=_OUTPUT_MODELS[name].model_json_schema(),
    )
    for name, summary, data_class, effects, network, cost, implemented, milestone in _ROWS
]
