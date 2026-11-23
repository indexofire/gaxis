"""Kernel service: the seven tool contracts implemented once, host-agnostic.

Every entry point here is transport-neutral. The MCP server, the CLI and any
host adapter call these functions; none of them know a host exists.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .acquire.download import download_pdf
from .acquire.identifiers import SourceKind, classify_source, needs_network, normalise
from .acquire.metadata import ResolutionError, resolve
from .acquire.paper import ingest_pdf, load_manifest, manifest_filename
from .acquire.repo import (
    ScriptCandidate,
    clone_repository,
    dependency_profile,
    find_repository_urls,
    inventory_repository,
)
from .adapt import adapt_script, delimiter_for
from .analysis import (
    check_workflow,
    list_recipes,
    list_workflows,
    run_amr_cooccurrence,
    run_newick_to_table,
    scaffold_snp_tree,
)
from .compose import collect_panels, compose_panels, page_geometry
from .config import settings
from .design import apply_plate_policy
from .design_judge import DesignJudgeError, HeuristicJudge, build_judge
from .errors import GaxisError
from .exec.runner import run_script
from .figures import load_figure_recipes
from .kb.adopt import AdoptedTemplate, adopt_asset, rewrite_path_interface
from .kb.base import KbError, KbStatus, try_get_page
from .kb.feedback import record_selection
from .kb.gbrain import GbrainCLI
from .kb.ingest import IngestSummary, KbIngestor
from .kb.names import template_slug
from .kb.search import search_assets
from .models.analysis import AmrCooccurrenceParams, AnalysisRun
from .models.composition import CompositionManifest
from .models.lint import LintReport
from .models.manifest import FigureManifest, FigureSource, OutputFile
from .models.paper import ChartReproManifest, CodeCandidate
from .models.recipe import (
    ListFigureRecipesRequest,
    ListFigureRecipesResult,
    RenderFigureRecipeRequest,
    RenderFigureRecipeResult,
)
from .models.reconstruct import ReconstructResult
from .models.schema import ColumnKind, DataSchema, describe_data
from .models.spec import ChartSpec, ChartType
from .models.tools import (
    TOOL_SPECS,
    AdaptChartCodeRequest,
    AdaptChartCodeResult,
    ChartAssetSummary,
    DescribeDataRequest,
    DescribeDataResult,
    FigureBrief,
    GetChartManifestRequest,
    GetChartManifestResult,
    HealthStatus,
    IngestPaperRequest,
    IngestPaperResult,
    PlanChartRequest,
    PlanChartResult,
    RenderRequest,
    RenderResult,
    ReproduceChartCodeRequest,
    ReproduceChartCodeResult,
    SearchChartAssetsRequest,
    SearchChartAssetsResult,
)
from .models.workflow import WorkflowScaffold
from .quality import (
    CalibrationReport,
    CalibrationRow,
    QualityWeights,
    apply_category_policy,
    build_sheet,
    calibrate,
    design_tier,
    score_manifest,
)
from .render.emit import emit_code
from .repro.reconstruct import reconstruct_manifest
from .repro.runner import reproduce_manifest
from .spec.brief import build_plan, detect_chart_type
from .spec.infer import infer_spec
from .style.lint import lint_outputs, measure_output
from .style.palettes import get_palette, palette_names
from .style.presets import load_preset, preset_names, resolve_size
from .style.rc import resolve_font
from .usefulness import score_usefulness, usefulness_components, usefulness_notes

logger = logging.getLogger(__name__)

CODE_NAMES = {"python": "figure.py", "r": "figure.R"}
# Bump when templates or emission change, so cached figure ids never point at stale code.
PIPELINE_VERSION = 1


def describe(request: DescribeDataRequest) -> DescribeDataResult:
    """`describe_data_schema`: profile a table and suggest a chart."""
    try:
        schema = describe_data(request.data_path)
    except FileNotFoundError as exc:
        raise GaxisError("data_not_found", str(exc)) from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise GaxisError("data_unreadable", str(exc), hint="expected a UTF-8 CSV/TSV") from exc
    spec = infer_spec(schema, preset="default")
    return DescribeDataResult(
        data_schema=schema, suggested_spec=spec, summary=schema.summary_markdown()
    )


def _quality_weights() -> QualityWeights:
    quality = settings().config.quality
    return QualityWeights(**quality.model_dump())


def quality_sheet(
    out_dir: Path | None = None,
    limit: int = 30,
    force: bool = False,
    sort_by: str = "design",
    min_design: float = 0.0,
) -> tuple[Path, Path | None]:
    """Write the human-ranking sheet for the manifests currently on disk."""
    conf = settings()
    manifests = []
    for path in sorted(conf.manifests_dir.glob("*.json")):
        try:
            manifests.append(
                ChartReproManifest.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except ValueError:
            continue
    if not manifests:
        raise GaxisError(
            "no_manifests",
            "no manifests on disk",
            hint="run ingest_paper on a few PDFs first",
        )
    try:
        return build_sheet(
            manifests,
            data_root=conf.data_root,
            out_dir=out_dir or conf.data_root / "calibration",
            limit=limit,
            weights=_quality_weights(),
            force=force,
            sort_by=sort_by,
            min_design=min_design,
        )
    except FileExistsError as exc:
        raise GaxisError(
            "sheet_has_ranks",
            str(exc),
            hint="move the ranked sheet aside, or pass --force to overwrite deliberately",
        ) from exc
    return build_sheet(
        manifests,
        data_root=conf.data_root,
        out_dir=out_dir or conf.data_root / "calibration",
        limit=limit,
        weights=_quality_weights(),
        force=force,
    )


def quality_backfill(workers: int = 4, force: bool = False) -> dict[str, int]:
    """Recompute crop quality + design for existing manifests (concurrent judging)."""
    import concurrent.futures

    conf = settings()
    weights = _quality_weights()
    from .quality_image import crop_clean_score

    jobs: list[tuple[Path, ChartReproManifest, Path]] = []
    skipped = 0
    for path in sorted(conf.manifests_dir.glob("*.json")):
        try:
            manifest = ChartReproManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            skipped += 1
            continue
        geometry = manifest.geometry
        if geometry is None or not manifest.chart_file:
            skipped += 1
            continue
        image = conf.data_root / manifest.chart_file
        if not image.is_file():
            skipped += 1
            continue
        jobs.append((path, manifest, image))

    active = build_judge(conf)
    updated = 0

    def _process(job: tuple[Path, ChartReproManifest, Path]) -> ChartReproManifest:
        _, manifest, image = job
        geometry = manifest.geometry
        if geometry is None:  # jobs are pre-filtered; keeps the worker total
            return manifest
        geometry.crop_clean = crop_clean_score(image)
        manifest.chart_quality_score = score_manifest(manifest, weights, data_root=conf.data_root)
        if force or manifest.design is None or manifest.design.method == "objective":
            try:
                manifest.design = active.judge(image, caption=manifest.caption)
            except DesignJudgeError as exc:
                fallback = HeuristicJudge().judge(image, caption=manifest.caption)
                fallback.notes = [f"vision judge unavailable: {exc}", *fallback.notes]
                manifest.design = fallback
            manifest.design = apply_plate_policy(
                manifest.design, skip_plates=conf.config.design.skip_plates
            )
            manifest.design = apply_category_policy(
                manifest.design, allow_nonchart=conf.config.design.allow_nonchart
            )
            manifest.design.tier = design_tier(  # type: ignore[assignment]
                manifest.design.score,
                gold=conf.config.design.gold_score,
                dense=conf.config.design.dense_score,
            )
        from .models.paper import Usefulness

        manifest.usefulness = Usefulness(
            score=score_usefulness(manifest),
            components=usefulness_components(manifest),
            notes=usefulness_notes(manifest),
        )
        return manifest

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(_process, jobs))
    for (path, _manifest, _image), manifest in zip(jobs, results, strict=False):
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        updated += 1
    if updated and conf.config.knowledge.auto_ingest:
        kb_ingest(force=True)
    return {"updated": updated, "skipped": skipped}


def quality_calibrate(rankings: list[tuple[str, int]]) -> CalibrationReport:
    """Score weights against a human ranking (see docs/quality-calibration.md)."""
    conf = settings()
    manifests: dict[str, ChartReproManifest] = {}
    for path in sorted(conf.manifests_dir.glob("*.json")):
        try:
            stored = ChartReproManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        manifests[stored.manifest_id] = stored
    rows: list[CalibrationRow] = []
    missing: list[str] = []
    for manifest_id, rank in rankings:
        found = manifests.get(manifest_id)
        if found is None:
            missing.append(manifest_id)
            continue
        from .quality import components_from_manifest

        rows.append(
            CalibrationRow(
                manifest_id=manifest_id,
                components=components_from_manifest(found, data_root=conf.data_root),
                human_rank=rank,
            )
        )
    if missing:
        raise GaxisError(
            "unknown_manifest",
            f"{len(missing)} ranked id(s) are not on disk",
            hint=", ".join(missing[:5]),
        )
    if len(rows) < 5:
        raise GaxisError(
            "insufficient_samples",
            f"need at least 5 ranked figures, got {len(rows)}",
            hint="rank 20-30 figures for a trustworthy calibration",
        )
    return calibrate(rows, baseline=_quality_weights())


def knowledge() -> GbrainCLI | None:
    """The configured knowledge base, or None when it is disabled."""
    conf = settings().config
    if not conf.knowledge.enabled:
        return None
    return GbrainCLI(conf.knowledge)


def kb_status() -> KbStatus:
    kb = knowledge()
    if kb is None:
        return KbStatus(available=False, source="disabled", message="knowledge base disabled")
    return kb.status()


def search_chart_assets(request: SearchChartAssetsRequest) -> SearchChartAssetsResult:
    """`search_chart_assets`: text, schema or image retrieval over the paper KB.

    Degrades instead of failing: an empty or unavailable brain is reported as
    ``degraded: true`` so a host can fall back to builtin templates.
    """
    query = request.query.strip()
    chart_filter = request.chart_type.value if request.chart_type else None
    if request.schema_path:
        schema = describe_data(request.schema_path)
        inferred = infer_spec(schema, preset=request.preset or "default")
        chart_filter = chart_filter or inferred.chart_type.value
        parts = [f"{inferred.chart_type.value} figure"]
        if inferred.x:
            parts.append(f"x {inferred.x}")
        if inferred.y:
            parts.append(f"y {inferred.y}")
        if inferred.hue:
            parts.append(f"grouped by {inferred.hue}")
        parts.extend(column.kind.value for column in schema.columns)
        query = query or " ".join(parts)
    if not query:
        raise GaxisError(
            "bad_parameter",
            "give a query, a schema_path, or both",
            hint="a table profile is enough: search_chart_assets(schema_path=...)",
        )
    kb = knowledge()
    if kb is None:
        return SearchChartAssetsResult(
            degraded=True, message="knowledge base disabled ([knowledge] enabled = false)"
        )
    conf = settings()
    image = Path(request.query_image_path).expanduser() if request.query_image_path else None
    filters = {
        "chart_type": chart_filter,
        "min_level": request.min_reproduction_level,
        "preset": request.preset,
        "design_tier": request.design_tier,
        "has_code": request.has_code,
        "dedupe": request.dedupe,
        "types": conf.config.knowledge.types,
        "data_root": conf.data_root,
        "query_image": image,
    }
    try:
        assets = search_assets(kb, query, k=request.k, **filters)  # type: ignore[arg-type]
        note = ""
        if not assets and chart_filter:
            # a strict filter must not hide a good textual match; say so instead of "nothing"
            fallback = dict(filters)
            fallback["chart_type"] = None
            assets = search_assets(kb, query, k=request.k, **fallback)  # type: ignore[arg-type]
            if assets:
                note = f"no '{chart_filter}' asset matched; showing textual matches instead"
    except KbError as exc:
        return SearchChartAssetsResult(degraded=True, message=f"knowledge base unavailable: {exc}")
    sheet_path = _candidate_sheet(assets) if request.render_sheet else None
    message = note or ("" if assets else "no matching assets in the knowledge base yet")
    return SearchChartAssetsResult(
        assets=assets,
        total=len(assets),
        degraded=False,
        message=message,
        sheet_path=sheet_path,
    )


def _candidate_sheet(assets: list[ChartAssetSummary]) -> str | None:
    """Contact sheet for human selection; images are numbered and labelled."""
    from .design import build_candidate_sheet

    paths = [Path(asset.thumb_path) for asset in assets if asset.thumb_path]
    if not paths:
        return None
    conf = settings()
    digest = hashlib.sha256("|".join(asset.asset_id for asset in assets).encode()).hexdigest()[:10]
    out_dir = conf.data_root / "kb" / "sheets" / f"search-{digest}"
    try:
        _sheet, _csv, contact = build_candidate_sheet(paths, out_dir=out_dir, limit=40)
    except Exception as exc:  # noqa: BLE001 - a sheet is a convenience, not evidence
        logger.warning("candidate sheet failed: %s", exc)
        return None
    return str(contact)


def _ingest_manifests(manifests: list[ChartReproManifest], *, force: bool = False) -> IngestSummary:
    conf = settings()
    kb = knowledge()
    if kb is None:
        return IngestSummary(source="disabled", unavailable="knowledge base disabled")
    rejected: list[str] = []
    if not conf.config.knowledge.include_rejected_design:
        rejected = [
            manifest.manifest_id
            for manifest in manifests
            if manifest.design and manifest.design.tier == "reject"
        ]
        manifests = [manifest for manifest in manifests if manifest.manifest_id not in rejected]
    ingestor = KbIngestor(kb, state_path=conf.data_root / "kb" / "state.json")
    summary = ingestor.ingest(manifests, force=force)
    if rejected:
        # a re-judged figure that fell below the threshold must leave the index
        summary.removed = ingestor.forget(rejected)
    return summary


def kb_ingest(force: bool = False) -> IngestSummary:
    """Ingest every manifest on disk into the knowledge base (idempotent)."""
    conf = settings()
    kb = knowledge()
    if kb is None:
        return IngestSummary(source="disabled", unavailable="knowledge base disabled")
    manifests: list[ChartReproManifest] = []
    for path in sorted(conf.manifests_dir.glob("*.json")):
        try:
            manifests.append(
                ChartReproManifest.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except ValueError:
            continue
    return _ingest_manifests(manifests, force=force)


def plan_chart(request: PlanChartRequest) -> PlanChartResult:
    """`plan_chart_from_brief`: converge on a figure before any data exists."""
    if not request.brief.strip():
        raise GaxisError("bad_parameter", "brief must not be empty")
    if request.preset and request.preset not in preset_names():
        raise GaxisError(
            "bad_parameter",
            f"unknown preset '{request.preset}'",
            hint=f"available presets: {preset_names()}",
        )
    plan = build_plan(request.brief, preset=request.preset, backend=request.backend)
    matches: list[ChartAssetSummary] = []
    kb_note = ""
    kb = knowledge()
    stated_chart = detect_chart_type(request.brief)
    if kb is not None:
        conf = settings()
        try:
            matches = search_assets(
                kb,
                request.brief,
                k=request.k,
                chart_type=stated_chart.value if stated_chart else None,
                types=conf.config.knowledge.types,
                data_root=conf.data_root,
            )
        except KbError as exc:
            kb_note = f"knowledge base unavailable: {exc}"
    if matches:
        plan = plan.model_copy(
            update={
                "candidate_asset_ids": [asset.asset_id for asset in matches],
                "confidence": round(min(0.9, plan.confidence + 0.05 * min(len(matches), 3)), 2),
            }
        )
    policy = settings().config.confirmation
    if policy.mode == "always":
        requires_confirmation = True
    elif policy.mode == "never":
        requires_confirmation = False
    else:
        requires_confirmation = plan.confidence < policy.min_confidence
    if kb is None:
        message = "knowledge base disabled: the plan comes from the brief alone"
    elif kb_note:
        message = kb_note
    elif matches:
        message = f"{len(matches)} knowledge-base case(s) attached"
    else:
        message = "no knowledge-base case matched; plan from the brief alone"
    return PlanChartResult(
        plan=plan,
        matches=matches,
        degraded=kb is None or bool(kb_note),
        requires_confirmation=requires_confirmation,
        confirmation_threshold=policy.min_confidence,
        confirmation_mode=policy.mode,
        message=message,
    )


def ingest_paper(request: IngestPaperRequest) -> IngestPaperResult:
    """`ingest_paper`: classify the source now; parse/reproduce at M1/M2.

    The classification half is real work: it tells the host whether the source needs the
    network, what id to deduplicate on, and whether a knowledge-base-first reply is
    possible without downloading anything.
    """
    kind: SourceKind = classify_source(request.source)
    cfg = settings().config.ingest
    if kind is SourceKind.unknown:
        raise GaxisError(
            "unrecognised_source",
            f"cannot tell what kind of source this is: {request.source!r}",
            hint="pass a PDF path, DOI (10.xxxx/...), arXiv id, PubMed/PMC id, or an http(s) URL",
        )
    network = needs_network(kind)
    if network and not cfg.allow_network:
        raise GaxisError(
            "network_disabled",
            f"source kind '{kind}' requires network resolution but ingest.allow_network=false",
            hint="set [ingest] allow_network = true in gaxis.toml, or pass a local PDF",
        )
    mode = request.mode or cfg.default_mode

    if kind is SourceKind.pdf:
        path = Path(request.source).expanduser()
        if not path.is_file():
            raise GaxisError("data_not_found", f"PDF not found: {path}")
        conf = settings()
        try:
            record, manifests, parsed = ingest_pdf(
                path,
                assets_root=conf.assets_dir,
                manifests_dir=conf.manifests_dir,
                persist=mode == "full",
                min_quality=max(request.min_quality, cfg.min_quality),
            )
        except GaxisError:
            raise
        except Exception as exc:  # PyMuPDF raises its own error types
            raise GaxisError(
                "pdf_unreadable",
                f"cannot parse {path.name}: {exc}",
                hint="encrypted, corrupt, or not actually a PDF",
            ) from exc
        repository_urls = [link.url for link in find_repository_urls(parsed.full_text)]
        wants_code = request.with_code if request.with_code is not None else cfg.with_code
        code_candidates = 0
        if wants_code and repository_urls and mode == "full":
            code_candidates = _attach_repository_code(
                repository_urls,
                manifests,
                manifests_dir=conf.manifests_dir,
                data_root=conf.data_root,
                timeout_s=cfg.repo_timeout_s,
                max_repos=cfg.max_repos,
                notes=[],
            )
        briefs = [
            FigureBrief(
                figure_ref=figure.figure_ref,
                caption=figure.caption[:400],
                chart_type_guess=detect_chart_type(figure.caption),
                kb_match_asset_ids=[],
                needs_deep_parse=mode == "kb_first",
            )
            for figure in parsed.figures
        ]
        message = (
            f"parsed {parsed.page_count} page(s), found {len(parsed.figures)} figure(s); "
            "knowledge base has no matching assets yet (M3), so nothing to "
            "show instead of the paper"
            if mode == "kb_first"
            else (
                f"parsed {parsed.page_count} page(s), wrote {len(manifests)} manifest(s); "
                "run reproduce_chart_code to sandbox and grade them"
            )
        )
        if mode == "full" and manifests and conf.config.knowledge.auto_ingest:
            summary = _ingest_manifests(manifests)
            message = f"{message}; {summary.message()}"
        return IngestPaperResult(
            source=request.source,
            source_kind="pdf",
            normalised_id=record.paper_id,
            mode=mode,
            needs_network=False,
            paper_id=record.paper_id,
            title=record.title,
            doi=record.doi,
            repository_urls=repository_urls,
            code_candidate_count=code_candidates,
            figure_briefs=briefs,
            matches=[],
            manifest_ids=[m.manifest_id for m in manifests] if mode == "full" else [],
            charts_found=len(parsed.figures),
            reproduced={},
            deep_parse_suggested=mode == "kb_first",
            not_implemented=False,
            message=message,
        )

    identifier = normalise(request.source)
    try:
        metadata = resolve(kind.value, identifier, email=cfg.contact_email)
    except ResolutionError as exc:
        raise GaxisError(
            "resolution_failed",
            f"could not resolve {kind} {identifier!r}: {exc}",
            hint="check the identifier; for paywalled papers supply the PDF directly",
        ) from exc
    notes = [f"resolved {kind} via metadata service"]
    if metadata.note:
        notes.append(metadata.note)
    pdf_url = metadata.pdf_url
    if not pdf_url:
        return IngestPaperResult(
            source=request.source,
            source_kind=kind.value,  # type: ignore[arg-type]
            normalised_id=identifier,
            mode=mode,
            needs_network=True,
            paper_id="",
            title=metadata.title or None,
            doi=metadata.doi or None,
            pdf_url=None,
            deep_parse_suggested=mode == "kb_first",
            not_implemented=False,
            message=(
                "resolved metadata but found no open-access PDF: "
                + (metadata.note or "no PDF URL discovered")
                + "; download the PDF and pass it as a path"
            ),
        )
    conf = settings()
    try:
        pdf_path = download_pdf(
            pdf_url,
            conf.data_root / "papers",
            identifier=identifier,
            max_mb=cfg.max_download_mb,
        )
    except ResolutionError as exc:
        raise GaxisError(
            "download_failed",
            f"could not download the PDF for {identifier!r}: {exc}",
            hint="pass a local PDF path instead",
        ) from exc
    notes.append(f"downloaded {pdf_path.name}")
    try:
        record, manifests, parsed = ingest_pdf(
            pdf_path,
            assets_root=conf.assets_dir,
            manifests_dir=conf.manifests_dir,
            persist=mode == "full",
            min_quality=max(request.min_quality, cfg.min_quality),
            weights=_quality_weights(),
            judge=build_judge(conf),
            gold_score=conf.config.design.gold_score,
            dense_score=conf.config.design.dense_score,
            skip_plates=conf.config.design.skip_plates,
            allow_nonchart=conf.config.design.allow_nonchart,
        )
    except GaxisError:
        raise
    except Exception as exc:  # PyMuPDF raises its own error types
        raise GaxisError("pdf_unreadable", f"cannot parse downloaded PDF: {exc}") from exc

    if not record.title and metadata.title:
        record = record.__class__(
            paper_id=record.paper_id,
            title=metadata.title,
            sha256=record.sha256,
            source_path=record.source_path,
            page_count=record.page_count,
            doi=record.doi or metadata.doi,
        )
    repository_urls = [link.url for link in find_repository_urls(parsed.full_text)]
    code_candidates = 0
    wants_code = request.with_code if request.with_code is not None else cfg.with_code
    if wants_code and repository_urls and mode == "full":
        code_candidates = _attach_repository_code(
            repository_urls,
            manifests,
            manifests_dir=conf.manifests_dir,
            data_root=conf.data_root,
            timeout_s=cfg.repo_timeout_s,
            max_repos=cfg.max_repos,
            notes=notes,
        )
    if mode == "full" and manifests and conf.config.knowledge.auto_ingest:
        summary = _ingest_manifests(manifests)
        notes.append(summary.message())
    briefs = [
        FigureBrief(
            figure_ref=figure.figure_ref,
            caption=figure.caption[:400],
            chart_type_guess=detect_chart_type(figure.caption),
            kb_match_asset_ids=[],
            needs_deep_parse=mode == "kb_first",
        )
        for figure in parsed.figures
    ]
    return IngestPaperResult(
        source=request.source,
        source_kind=kind.value,  # type: ignore[arg-type]
        normalised_id=record.paper_id,
        mode=mode,
        needs_network=True,
        paper_id=record.paper_id,
        title=record.title or metadata.title or None,
        doi=record.doi or metadata.doi or None,
        pdf_url=pdf_url,
        repository_urls=repository_urls,
        code_candidate_count=code_candidates,
        figure_briefs=briefs,
        manifest_ids=[m.manifest_id for m in manifests] if mode == "full" else [],
        charts_found=len(parsed.figures),
        deep_parse_suggested=mode == "kb_first",
        not_implemented=False,
        message="; ".join(notes),
    )


def _caption_tokens(text: str) -> set[str]:
    cleaned = "".join(char if char.isalnum() else " " for char in text.lower())
    return {word for word in cleaned.split() if len(word) > 3}


def _best_script(scripts: list[ScriptCandidate], caption: str) -> ScriptCandidate | None:
    tokens = _caption_tokens(caption)
    best: tuple[float, ScriptCandidate] | None = None
    for script in scripts:
        name_tokens = _caption_tokens(script.relative_path)
        overlap = len(tokens & name_tokens)
        score = script.score + 0.15 * overlap
        if best is None or score > best[0]:
            best = (score, script)
    return best[1] if best else None


def _attach_repository_code(
    repository_urls: list[str],
    manifests: list[ChartReproManifest],
    *,
    manifests_dir: Path,
    data_root: Path,
    timeout_s: float,
    max_repos: int,
    notes: list[str],
) -> int:
    """Clone candidate repositories and attach plotting scripts to the manifests."""
    from .acquire.repo import RepoLink

    attached = 0
    for url in repository_urls[:max_repos]:
        link = RepoLink(
            url=url,
            host="github" if "github.com" in url else "unknown",
            owner=url.rstrip("/").split("/")[-2] if url.count("/") >= 4 else "",
            repo=url.rstrip("/").split("/")[-1],
        )
        try:
            repo_path = clone_repository(link, data_root / "repos", timeout_s=timeout_s, max_mb=200)
        except RuntimeError as exc:
            notes.append(f"repo {link.name} not cloned: {exc}")
            continue
        inventory = inventory_repository(link, repo_path)
        if not inventory.scripts:
            notes.append(f"repo {link.name}: no plotting scripts found")
            continue
        for manifest in manifests:
            script = _best_script(inventory.scripts, manifest.caption)
            if script is None:
                continue
            candidate = CodeCandidate(
                code_path=str(script.path),
                language=script.language,  # type: ignore[arg-type]
                entry_point=script.relative_path,
                dependency_hints=list(script.markers),
                packages=dependency_profile(
                    repo_path, language="r" if script.language == "r" else "python"
                ),
                license=inventory.license,
                pairing_confidence=round(min(script.score, 0.95), 2),
            )
            manifest.code_candidates = [
                existing
                for existing in manifest.code_candidates
                if existing.code_path != candidate.code_path
            ] + [candidate]
            manifest_path = manifests_dir / manifest_filename(manifest.manifest_id)
            if manifest_path.parent.is_dir():
                manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            attached += 1
        notes.append(
            f"repo {link.name}: {len(inventory.scripts)} plotting script(s), "
            f"licence {inventory.license or 'unknown'}"
        )
    return attached


def render(request: RenderRequest, *, execute: bool = True) -> RenderResult:
    """`render_chart_from_data`: data in, journal figure + code out.

    ``execute=False`` emits the script and manifest without running it (dry run).
    """
    schema = describe_data(request.data_path)
    spec = infer_spec(
        schema,
        chart_type=request.chart_type,
        x=request.x,
        y=request.y,
        hue=request.hue,
        yerr=request.yerr,
        weight=request.weight,
        annotations=list(request.annotations),
        color_map=dict(request.color_map),
        title=request.title,
        xlabel=request.xlabel,
        ylabel=request.ylabel,
        preset=request.preset,
        palette=request.palette,
        backend=request.backend,
        width_mm=request.width_mm,
        height_mm=request.height_mm,
        dpi=request.dpi,
        formats=request.formats,
        annotate_values=request.annotate_values,
    )
    out_dir = Path(request.out_dir).expanduser().resolve() if request.out_dir else None
    result = render_spec(
        schema,
        spec,
        out_dir=out_dir,
        asset_ids=[request.source_asset] if request.source_asset else None,
        execute=execute,
    )
    if request.source_asset:
        record_selection(
            settings().data_root,
            asset_id=request.source_asset,
            action="render",
            figure_id=result.figure_id,
            preset=spec.preset,
            chart_type=spec.chart_type.value,
        )
    return result


def validate(spec: ChartSpec, schema: DataSchema) -> None:
    available = [c.name for c in schema.columns]
    for field in ("x", "y", "hue", "yerr", "weight"):
        name = getattr(spec, field)
        if name and not schema.has(name):
            raise GaxisError(
                "unknown_column",
                f"{field} column '{name}' is not in the table",
                hint=f"available columns: {available}",
            )
    for column in spec.annotations:
        if not schema.has(column):
            raise GaxisError(
                "unknown_column",
                f"annotation column '{column}' is not in the table",
                hint=f"available columns: {available}",
            )
    if spec.x is None:
        raise GaxisError(
            "missing_x", "no x column could be inferred", hint=f"available: {available}"
        )
    for field in ("y", "yerr", "weight"):
        if field == "y" and spec.chart_type in (ChartType.network, ChartType.tree):
            continue
        name = getattr(spec, field)
        profile = schema.column(name) if name else None
        if profile and profile.kind is not ColumnKind.numeric:
            raise GaxisError(
                "not_numeric", f"{field} column '{name}' is {profile.kind}, not numeric"
            )
    if (
        spec.chart_type
        in (
            ChartType.scatter,
            ChartType.box,
            ChartType.heatmap,
            ChartType.network,
        )
        and not spec.y
    ):
        raise GaxisError(
            "missing_y",
            f"{spec.chart_type.value} needs a numeric y column",
            hint=f"numeric: {schema.numeric_columns}",
        )


def _figure_id(schema: DataSchema, spec: ChartSpec) -> str:
    payload = f"{PIPELINE_VERSION}:{schema.sha256}:{spec.model_dump_json()}"
    digest = hashlib.sha256(payload.encode()).hexdigest()[:10]
    return f"{spec.chart_type.value}-{digest}"


def _style_summary(
    spec: ChartSpec, preset_name: str, palette: str, width_mm: float, height_mm: float
) -> dict[str, Any]:
    preset = load_preset(preset_name)
    return {
        "preset": preset.name,
        "preset_label": preset.label,
        "publisher": preset.publisher,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "dpi": spec.dpi,
        "palette": palette,
        "font": resolve_font(tuple(preset.font_family)),
        "base_font_pt": preset.base_font_pt,
        "backend": spec.backend,
    }


def render_spec(
    schema: DataSchema,
    spec: ChartSpec,
    *,
    out_dir: Path | None = None,
    source: FigureSource = "builtin_templates",
    asset_ids: list[str] | None = None,
    execute: bool = True,
    code_adapter: Callable[[str, Path, Path], str] | None = None,
) -> RenderResult:
    """Shared render path: used by builtin templates today, KB adaptation at M4."""
    validate(spec, schema)
    cfg = settings()
    preset = load_preset(spec.preset)
    width_mm, height_mm = resolve_size(spec, preset)
    palette = get_palette(spec.palette or preset.palette)
    spec = spec.model_copy(update={"palette": palette.name})
    figure_id = _figure_id(schema, spec)

    fig_dir = (out_dir or cfg.renders_dir) / figure_id
    fig_dir.mkdir(parents=True, exist_ok=True)
    code_path = fig_dir / CODE_NAMES[spec.backend]
    code_text = emit_code(
        spec=spec,
        schema=schema,
        preset=preset,
        width_mm=width_mm,
        height_mm=height_mm,
        data_path=Path(schema.path),
        out_dir=fig_dir,
        stem=figure_id,
    )
    if code_adapter is not None:
        code_text = code_adapter(code_text, fig_dir, Path(schema.path))
    code_path.write_text(code_text, encoding="utf-8")
    if not execute:
        return RenderResult(
            figure_id=figure_id,
            manifest_path="",
            manifest=FigureManifest(
                figure_id=figure_id,
                spec=spec,
                data=schema,
                preset=preset.name,
                backend=spec.backend,
                style=_style_summary(spec, preset.name, palette.name, width_mm, height_mm),
                code_path=str(code_path),
                code_sha256=hashlib.sha256(code_path.read_bytes()).hexdigest(),
                source=source,
                asset_ids=asset_ids or [],
            ),
            code_path=str(code_path),
            outputs=[],
            lint=LintReport(),
            duration_s=0.0,
        )
    result = run_script(
        code_path, cwd=fig_dir, timeout_s=cfg.render_timeout_s, backend=spec.backend
    )
    log_path = fig_dir / "render.log"
    log_path.write_text(
        f"$ {code_path.name}\nexit={result.returncode}\n\n[stdout]\n{result.stdout}\n"
        f"[stderr]\n{result.stderr}\n",
        encoding="utf-8",
    )
    if not result.ok:
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-12:])
        raise GaxisError(
            "render_failed",
            f"{spec.backend} script exited {result.returncode}; see {log_path}",
            hint=tail,
        )

    paths = [fig_dir / f"{figure_id}.{fmt}" for fmt in spec.formats]
    outputs: list[OutputFile] = []
    for path in paths:
        if not path.is_file():
            continue
        width, height, dpi = measure_output(path)
        outputs.append(
            OutputFile(
                path=str(path),
                format=path.suffix.lstrip("."),
                bytes=path.stat().st_size,
                width_mm=width,
                height_mm=height,
                dpi=dpi,
            )
        )
    lint = lint_outputs(
        paths,
        preset=preset,
        spec=spec,
        expected_width_mm=width_mm,
        expected_height_mm=height_mm,
    )
    manifest = FigureManifest(
        figure_id=figure_id,
        spec=spec,
        data=schema,
        preset=preset.name,
        backend=spec.backend,
        style=_style_summary(spec, preset.name, palette.name, width_mm, height_mm),
        code_path=str(code_path),
        code_sha256=hashlib.sha256(code_path.read_bytes()).hexdigest(),
        outputs=outputs,
        lint=lint,
        source=source,
        asset_ids=asset_ids or [],
    )
    manifest_path = fig_dir / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return RenderResult(
        figure_id=figure_id,
        manifest_path=str(manifest_path),
        manifest=manifest,
        code_path=str(code_path),
        outputs=outputs,
        lint=lint,
        exec_stdout=result.stdout,
        exec_stderr=result.stderr,
        duration_s=result.duration_s,
    )


def lint_files(
    paths: list[Path],
    *,
    preset_name: str = "default",
    width_mm: float | None = None,
    height_mm: float | None = None,
) -> Any:
    preset = load_preset(preset_name)
    spec = ChartSpec(preset=preset_name)
    return lint_outputs(
        paths,
        preset=preset,
        spec=spec,
        expected_width_mm=width_mm or preset.width_single_mm,
        expected_height_mm=height_mm or preset.height_mm,
    )


def reproduce_chart_code(request: ReproduceChartCodeRequest) -> ReproduceChartCodeResult:
    """`reproduce_chart_code`: sandbox a paper figure's script, compare, grade."""
    conf = settings()
    manifest = load_manifest(request.manifest_id, conf.manifests_dir)
    if manifest is None:
        raise GaxisError(
            "manifest_not_found",
            f"no manifest named {request.manifest_id!r}",
            hint="run ingest_paper on the PDF first",
        )
    code = request.code_path or (
        manifest.code_candidates[-1].code_path if manifest.code_candidates else None
    )
    if not code:
        raise GaxisError(
            "code_required",
            "the manifest has no code candidate yet",
            hint="pass code_path (a local .py file) until repository parsing lands",
        )
    outcome = reproduce_manifest(
        manifest,
        manifest_path=conf.manifests_dir / manifest_filename(manifest.manifest_id),
        code_path=Path(code),
        data_path=Path(request.data_path) if request.data_path else None,
        engine=request.engine,
        timeout_s=request.timeout_s,
        allow_network=request.allow_network,
        data_root=conf.data_root,
        config=conf.config,
    )
    outcome.result.sandbox_report["kb_refresh"] = _kb_refresh(outcome.manifest)
    return outcome.result


def _kb_refresh(manifest: Any) -> str:
    """Project a freshly graded manifest into the KB; a failure is reported, not hidden."""
    kb = knowledge()
    if kb is None:
        return "skipped: knowledge base disabled"
    conf = settings()
    try:
        ingestor = KbIngestor(kb, state_path=conf.data_root / "kb" / "state.json")
        summary = ingestor.ingest([manifest])
    except KbError as exc:
        return f"failed: {exc}"
    if summary.failed:
        return "failed: " + summary.failed[0][1]
    return "refreshed" if summary.upserted else "unchanged"


def reconstruct_chart(
    manifest_id: str,
    *,
    data_path: Path | None = None,
    engine: str | None = None,
    rounds: int | None = None,
    target: float | None = None,
    repair: bool = False,
    model: str | None = None,
    timeout_s: float | None = None,
    max_side: int | None = None,
) -> ReconstructResult:
    """`reconstruct`: LLM writes (or repairs) a script; the sandbox grades it.

    This is the fallback for figures without runnable author code. It never labels the
    result as an author reproduction: ``reproduction.method`` and the generated code
    candidate record the provenance.
    """
    conf = settings()
    manifest = load_manifest(manifest_id, conf.manifests_dir)
    if manifest is None:
        raise GaxisError(
            "manifest_not_found",
            f"no paper figure manifest named {manifest_id!r}",
            hint="run `gaxis ingest` first",
        )
    if not manifest.chart_file:
        raise GaxisError(
            "reference_missing",
            f"{manifest_id} has no artwork to reconstruct from",
            hint="caption-only figures cannot be reconstructed",
        )
    reference = conf.data_root / manifest.chart_file
    repair_code = ""
    if repair:
        candidate = next(
            (item for item in reversed(manifest.code_candidates) if not item.generated), None
        )
        if candidate is None or not Path(candidate.code_path).is_file():
            raise GaxisError(
                "code_required",
                "repair needs an existing author script",
                hint="pass --code path/to/script or run without --repair to generate one",
            )
        repair_code = Path(candidate.code_path).read_text(encoding="utf-8")
    manifest_path = conf.manifests_dir / manifest_filename(manifest.manifest_id)
    try:
        outcome = reconstruct_manifest(
            manifest,
            manifest_path=manifest_path,
            reference=reference,
            data_path=Path(data_path).expanduser() if data_path else None,
            engine=engine,
            rounds=rounds or conf.config.reconstruct.max_rounds,
            target=target or conf.config.reconstruct.target_similarity,
            data_root=conf.data_root,
            config=conf.config,
            repair_code=repair_code,
            model_override=model,
            timeout_override=timeout_s,
            max_side_override=max_side,
        )
    except GaxisError:
        fallback = conf.config.reconstruct.fallback_model
        if not fallback or fallback == (model or conf.config.reconstruct.model):
            raise
        outcome = reconstruct_manifest(
            manifest,
            manifest_path=manifest_path,
            reference=reference,
            data_path=Path(data_path).expanduser() if data_path else None,
            engine=engine,
            rounds=rounds or conf.config.reconstruct.max_rounds,
            target=target or conf.config.reconstruct.target_similarity,
            data_root=conf.data_root,
            config=conf.config,
            repair_code=repair_code,
            model_override=fallback,
            timeout_override=timeout_s,
            max_side_override=max_side,
        )
        outcome.result.kb_refresh = _kb_refresh(outcome.manifest)
        return outcome.result

    fallback = conf.config.reconstruct.fallback_model
    primary_model = outcome.result.model
    if fallback and fallback != primary_model and outcome.result.level not in {"L1", "L2"}:
        snapshot = manifest_path.read_bytes() if manifest_path.is_file() else b""
        try:
            alternative = reconstruct_manifest(
                manifest,
                manifest_path=manifest_path,
                reference=reference,
                data_path=Path(data_path).expanduser() if data_path else None,
                engine=engine,
                rounds=rounds or conf.config.reconstruct.max_rounds,
                target=target or conf.config.reconstruct.target_similarity,
                data_root=conf.data_root,
                config=conf.config,
                repair_code=repair_code,
                model_override=fallback,
                timeout_override=timeout_s,
                max_side_override=max_side,
            )
        except GaxisError:
            if snapshot:
                manifest_path.write_bytes(snapshot)
            outcome.result.kb_refresh = _kb_refresh(outcome.manifest)
            return outcome.result
        better = (alternative.result.visual_similarity or -1) > (
            outcome.result.visual_similarity or -1
        )
        if better:
            outcome = alternative
        elif snapshot:
            manifest_path.write_bytes(snapshot)
            outcome.result.kb_refresh = _kb_refresh(outcome.manifest)
            return outcome.result
    outcome.result.kb_refresh = _kb_refresh(outcome.manifest)
    return outcome.result


def adopt_chart_asset(
    manifest_id: str,
    *,
    code_path: Path | None = None,
    preset: str = "default",
) -> AdoptedTemplate:
    """`kb adopt`: register a reproduced paper script as an adaptable template."""
    conf = settings()
    manifest = load_manifest(manifest_id, conf.manifests_dir)
    if manifest is None:
        raise GaxisError(
            "manifest_not_found",
            f"no paper figure manifest named {manifest_id!r}",
            hint="ingest the paper first, then reproduce a script",
        )
    kb = knowledge()
    if kb is None:
        raise GaxisError("kb_disabled", "knowledge base disabled ([knowledge] enabled = false)")
    return adopt_asset(
        kb,
        manifest=manifest,
        data_root=conf.data_root,
        code=code_path,
        preset=preset,
    )


def _run_path_template(
    *,
    schema: Any,
    spec: ChartSpec,
    template_code: str,
    asset_slug: str,
    fig_dir: Path,
) -> AdaptChartCodeResult:
    """Run an adopted paper script after rebinding its DATA_PATH (arbitrary outputs)."""
    cfg = settings()
    preset = load_preset(spec.preset)
    width_mm, height_mm = resolve_size(spec, preset)
    figure_id = _figure_id(schema, spec) + "-adopt"
    fig_dir = fig_dir / figure_id
    fig_dir.mkdir(parents=True, exist_ok=True)
    code_path = fig_dir / CODE_NAMES[spec.backend]
    adapted = rewrite_path_interface(
        template_code,
        backend=spec.backend,
        data_path=Path(schema.path),
        out_dir=fig_dir,
    )
    code_path.write_text(adapted, encoding="utf-8")
    result = run_script(
        code_path, cwd=fig_dir, timeout_s=cfg.render_timeout_s, backend=spec.backend
    )
    (fig_dir / "render.log").write_text(
        f"$ {code_path.name}\nexit={result.returncode}\n\n[stdout]\n{result.stdout}\n"
        f"[stderr]\n{result.stderr}\n",
        encoding="utf-8",
    )
    if not result.ok:
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-12:])
        raise GaxisError(
            "render_failed",
            f"adopted template exited {result.returncode}; see {fig_dir / 'render.log'}",
            hint=tail,
        )
    formats = ("pdf", "svg", "png", "tiff")
    produced = sorted(path for path in fig_dir.glob("*") if path.suffix.lstrip(".") in formats)
    outputs: list[OutputFile] = []
    for path in produced:
        width, height, dpi = measure_output(path)
        outputs.append(
            OutputFile(
                path=str(path),
                format=path.suffix.lstrip("."),
                bytes=path.stat().st_size,
                width_mm=width,
                height_mm=height,
                dpi=dpi,
            )
        )
    lint = lint_outputs(
        produced,
        preset=preset,
        spec=spec,
        expected_width_mm=width_mm,
        expected_height_mm=height_mm,
    )
    manifest = FigureManifest(
        figure_id=figure_id,
        spec=spec,
        data=schema,
        preset=preset.name,
        backend=spec.backend,
        style=_style_summary(
            spec, preset.name, spec.palette or preset.palette, width_mm, height_mm
        ),
        code_path=str(code_path),
        code_sha256=hashlib.sha256(code_path.read_bytes()).hexdigest(),
        outputs=outputs,
        lint=lint,
        source="kb_asset",
        asset_ids=[asset_slug],
    )
    (fig_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return AdaptChartCodeResult(
        figure_id=figure_id,
        code_path=str(code_path),
        outputs=outputs,
        lint=lint,
        source="kb_asset",
        asset_ids=[asset_slug],
        fallback_reason="",
        not_implemented=False,
    )


def adapt_chart_code(request: AdaptChartCodeRequest) -> AdaptChartCodeResult:
    """`adapt_chart_code`: retrieve a verified template from the KB and rebind it.

    The template's plotting code is reused verbatim; only the constants a human would
    edit (data path, output dir, stem, delimiter, encoding intent) are rewritten. When
    no suitable verified asset exists, the builtin emitter is used and the reason is
    reported — never silent.
    """
    conf = settings()
    schema = describe_data(request.data_path)
    spec = infer_spec(
        schema,
        preset=request.preset,
        backend=request.backend,
        formats=request.formats,
        dpi=request.dpi,
    )
    requested_chart = detect_chart_type(request.query) if request.query else None
    if requested_chart is not None:
        spec = spec.model_copy(update={"chart_type": requested_chart})

    kb = knowledge()
    asset_ids: list[str] = []
    fallback = ""
    template_code: str | None = None
    interface = "full"
    slug = ""
    if request.asset_id:
        slug = request.asset_id
        page = try_get_page(kb, slug) if kb is not None else None
        if page is None:
            fallback = f"asset {slug!r} not found in the knowledge base"
        elif _page_kind(page) != "template":
            fallback = (
                f"asset {slug!r} is a paper figure, not a template; "
                "paper-code adaptation lands after M4"
            )
        else:
            template_code = _template_code(page, conf.data_root)
            interface = str((page.get("frontmatter") or {}).get("interface") or "full")
    else:
        if kb is None:
            fallback = "knowledge base disabled ([knowledge] enabled = false)"
        else:
            slug = template_slug(spec.preset, spec.chart_type.value, spec.backend)
            page = try_get_page(kb, slug)
            if page is None:
                fallback = (
                    f"no verified template for preset={spec.preset} "
                    f"chart={spec.chart_type.value} backend={spec.backend}; run `gaxis kb seed`"
                )
            else:
                template_code = _template_code(page, conf.data_root)
                interface = str((page.get("frontmatter") or {}).get("interface") or "full")
    if template_code is None and not fallback:
        fallback = "template page carries no code"

    if template_code is not None and interface == "path":
        return _run_path_template(
            schema=schema,
            spec=spec,
            template_code=template_code,
            asset_slug=slug,
            fig_dir=settings().renders_dir,
        )

    adapter = None
    if template_code is not None:
        applied: list[str] = []

        def adapter(text: str, fig_dir: Path, data_path: Path) -> str:
            adapted, rewrites = adapt_script(
                template_code,
                backend=spec.backend,
                spec=spec,
                data_path=data_path,
                out_dir=fig_dir,
                stem=fig_dir.name,
                delimiter=delimiter_for(data_path),
            )
            applied.extend(rewrites)
            return adapted

        source: FigureSource = "kb_asset"
        asset_ids = [slug]
    else:
        source = "builtin_templates"

    result = render_spec(
        schema,
        spec,
        source=source,
        asset_ids=asset_ids,
        execute=not request.dry_run,
        code_adapter=adapter,
    )
    if asset_ids:
        record_selection(
            conf.data_root,
            asset_id=asset_ids[0],
            action="adapt",
            figure_id=result.figure_id,
            preset=spec.preset,
            chart_type=spec.chart_type.value,
        )
    return AdaptChartCodeResult(
        figure_id=result.figure_id,
        code_path=result.code_path,
        outputs=result.outputs,
        lint=result.lint,
        source="kb_asset" if asset_ids else "builtin_templates",
        asset_ids=asset_ids,
        fallback_reason=fallback,
        not_implemented=False,
    )


def _page_kind(page: dict[str, Any]) -> str:
    front = page.get("frontmatter") or {}
    return str(page.get("type") or front.get("type") or "")


def _template_code(page: dict[str, Any], data_root: Path) -> str | None:
    front = page.get("frontmatter") or {}
    relative = front.get("code_path")
    if relative:
        path = data_root / str(relative)
        if path.is_file():
            return path.read_text(encoding="utf-8")
    body = str(page.get("compiled_truth") or "")
    if "```" in body:
        blocks = body.split("```")
        if len(blocks) >= 2:
            block = blocks[1]
            return block.split("\n", 1)[1] if "\n" in block else block
    return None


def figure_recipes(request: ListFigureRecipesRequest | None = None) -> ListFigureRecipesResult:
    """Curated table -> figure recipes; no analysis is run here."""
    recipes = load_figure_recipes()
    if request and request.chart_type:
        recipes = [recipe for recipe in recipes if recipe.chart_type == request.chart_type]
    return ListFigureRecipesResult(recipes=recipes, total=len(recipes))


def render_figure_recipe(request: RenderFigureRecipeRequest) -> RenderFigureRecipeResult:
    """Render a curated recipe after checking its input contract."""
    recipe = next(
        (item for item in load_figure_recipes() if item.recipe_id == request.recipe_id),
        None,
    )
    if recipe is None:
        raise GaxisError(
            "unknown_recipe",
            f"unknown figure recipe {request.recipe_id!r}",
            hint="call list_figure_recipes",
        )
    schema = describe_data(request.data_path)
    missing = [name for name in recipe.required_columns if not schema.has(name)]
    if missing:
        raise GaxisError(
            "recipe_contract_violation",
            f"{recipe.recipe_id} requires columns {missing}",
            hint=f"available columns: {[column.name for column in schema.columns]}",
        )
    spec = infer_spec(
        schema,
        chart_type=recipe.chart_type,
        x=recipe.x,
        y=recipe.y,
        hue=recipe.hue,
        weight=recipe.weight,
        preset=request.preset or recipe.preset,
    ).model_copy(
        update={
            "annotations": list(recipe.annotations),
            "color_map": dict(request.color_map),
        }
    )
    result = render_spec(
        schema,
        spec,
        out_dir=Path(request.out_dir).expanduser().resolve() if request.out_dir else None,
        source="figure_recipe",
        execute=not request.dry_run,
    )
    result.manifest.recipe_id = recipe.recipe_id
    if result.manifest_path:
        Path(result.manifest_path).write_text(
            result.manifest.model_dump_json(indent=2), encoding="utf-8"
        )
    return RenderFigureRecipeResult(
        recipe_id=recipe.recipe_id,
        figure_id=result.figure_id,
        code_path=result.code_path,
        outputs=result.outputs,
        lint=result.lint,
        manifest=json.loads(result.manifest.model_dump_json()),
        source="figure_recipe",
        not_implemented=False,
    )


def analysis_recipes() -> list[dict[str, Any]]:
    """Available analysis recipes (table -> table); no algorithm is invented here."""
    return list_recipes()


def analysis_workflows() -> list[dict[str, Any]]:
    """Available Snakemake workflow recipes (scaffold + validate only)."""
    return list_workflows()


def analysis_scaffold(
    workflow: str,
    *,
    out_dir: Path,
    alignment: Path,
    metadata: Path | None = None,
    model: str = "GTR+G",
    bootstrap: int = 1000,
    threads: int = 4,
    seed: int = 42,
    container: str = "",
    check: bool = False,
) -> tuple[WorkflowScaffold, str]:
    """Generate a workflow project; optionally validate it with `snakemake -n`."""
    if workflow != "snp-tree":
        raise GaxisError("unknown_workflow", f"unknown workflow {workflow!r}")
    if check and not alignment.is_file():
        raise GaxisError("data_not_found", f"alignment not found: {alignment}")
    scaffold = scaffold_snp_tree(
        out_dir,
        alignment=alignment,
        metadata=metadata,
        model=model,
        bootstrap=bootstrap,
        threads=threads,
        seed=seed,
        container=container,
    )
    output = check_workflow(out_dir) if check else ""
    scaffold.check = output
    return scaffold, output


def analysis_run(
    recipe: str,
    *,
    input_path: Path,
    out_dir: Path | None = None,
    params: AmrCooccurrenceParams | None = None,
    metadata_path: Path | None = None,
) -> AnalysisRun:
    """Run an analysis recipe on the user's table and write nodes/edges."""
    conf = settings()
    target = (out_dir or (conf.data_root / "analysis")).expanduser().resolve()
    if recipe == "newick-to-table":
        return run_newick_to_table(input_path, out_dir=target, metadata_path=metadata_path)
    if recipe != "amr-cooccurrence":
        raise GaxisError(
            "unknown_recipe",
            f"unknown analysis recipe {recipe!r}",
            hint="run `gaxis analysis list`",
        )
    try:
        return run_amr_cooccurrence(input_path, out_dir=target, params=params)
    except FileNotFoundError as exc:
        raise GaxisError("data_not_found", str(exc)) from exc


def find_figure_manifest(identifier: str) -> FigureManifest:
    """Resolve a rendered figure by id (``renders/<id>/manifest.json``) or by path."""
    candidate = Path(identifier).expanduser()
    if candidate.is_file():
        return FigureManifest.model_validate_json(candidate.read_text())
    conf = settings()
    for candidate in (conf.renders_dir / identifier / "manifest.json",):
        if candidate.is_file():
            return FigureManifest.model_validate_json(candidate.read_text())
    matches = list(conf.data_root.rglob(f"{identifier}/manifest.json"))
    if matches:
        return FigureManifest.model_validate_json(matches[0].read_text())
    raise GaxisError(
        "figure_not_found",
        f"no rendered figure named {identifier!r}",
        hint="pass the figure id printed by `gaxis render`, or a path to its manifest.json",
    )


def compose(
    panel_ids: list[str],
    *,
    preset: str = "default",
    out_dir: Path | None = None,
    layout: tuple[int, int] | None = None,
    width_mm: float | None = None,
    height_mm: float | None = None,
    labels: bool = True,
    uniform: bool = False,
) -> CompositionManifest:
    """`compose_panels` (service form): arrange rendered figures on one page.

    ``uniform=True`` re-renders each panel from its manifest at the composition preset and
    cell size first, so type sizes and geometry match across panels.
    """
    if len(panel_ids) < 2:
        raise GaxisError("insufficient_panels", "composition needs at least two panels")
    conf = settings()
    manifests = [find_figure_manifest(identifier) for identifier in panel_ids]
    target = (out_dir or (conf.renders_dir / "compositions")).expanduser().resolve()
    if uniform:
        geometry = page_geometry(
            len(manifests),
            preset_name=preset,
            layout=layout,
            width_mm=width_mm,
            height_mm=height_mm,
        )
        rerendered = []
        for manifest in manifests:
            spec = manifest.spec.model_copy(
                update={
                    "preset": preset,
                    "width_mm": geometry.cell_w_mm,
                    "height_mm": geometry.cell_h_mm,
                    "formats": ["pdf"],
                }
            )
            rerendered.append(
                render_spec(
                    manifest.data,
                    spec,
                    out_dir=target / "panels",
                    source="builtin_templates",
                ).manifest
            )
        manifests = rerendered
    sources = collect_panels(manifests, conf.data_root)
    try:
        return compose_panels(
            sources,
            out_dir=target,
            preset_name=preset,
            layout=layout,
            width_mm=width_mm,
            height_mm=height_mm,
            labels=labels,
            uniform=uniform,
        )
    except KeyError as exc:
        raise GaxisError("bad_parameter", str(exc)) from exc


def get_chart_manifest(request: GetChartManifestRequest) -> GetChartManifestResult:
    """`get_chart_manifest`: read a persisted ChartReproManifest by id."""
    manifest = load_manifest(request.manifest_id, settings().manifests_dir)
    if manifest is None:
        return GetChartManifestResult(
            manifest_id=request.manifest_id,
            found=False,
            message=f"no manifest named {request.manifest_id!r}; run ingest_paper on the PDF first",
        )
    return GetChartManifestResult(
        manifest_id=request.manifest_id,
        found=True,
        manifest=manifest.model_dump(mode="json"),
    )


def health() -> HealthStatus:
    """`health`: read-only. Must never trigger a render or a network call."""
    cfg = settings()
    return HealthStatus(
        ok=True,
        data_root=str(cfg.data_root),
        python_backend=importlib.util.find_spec("matplotlib") is not None,
        r_backend=shutil.which("Rscript") is not None,
        presets=preset_names(),
        stages={
            spec.name: ("ready" if spec.implemented else f"planned {spec.milestone}")
            for spec in TOOL_SPECS
        },
        message=f"{len(palette_names())} palettes, {len(preset_names())} journal presets",
    )


def tool_catalog() -> list[dict[str, Any]]:
    """Machine-readable contract for hosts (bacmap maps this into its own profile gating)."""
    return [spec.model_dump(mode="json") for spec in TOOL_SPECS]
