"""CLI adapter (plan module G): a thin shell over ``gaxis.service``, nothing else."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer

from .. import __version__, service
from ..errors import GaxisError
from ..models.spec import ChartType
from ..models.tools import (
    DescribeDataRequest,
    GetChartManifestRequest,
    IngestPaperRequest,
    PlanChartRequest,
    RenderRequest,
    ReproduceChartCodeRequest,
    SearchChartAssetsRequest,
)
from ..service import lint_files, render
from ..style.palettes import PALETTES, palette_names
from ..style.presets import preset_table

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="gaxis — publication-grade figures, and the code that makes them",
)


@app.callback()
def main(
    config: Path | None = typer.Option(
        None, "--config", envvar="GAXIS_CONFIG", help="TOML config file (default: ./gaxis.toml)"
    ),
) -> None:
    """gaxis — figures, the code behind them, and the knowledge base that feeds them."""
    if config is not None:
        os.environ["GAXIS_CONFIG"] = str(config)


def _fail(exc: GaxisError) -> None:
    typer.echo(json.dumps(exc.as_dict(), ensure_ascii=False), err=True)
    raise typer.Exit(code=2)


def _echo_json(payload: object) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command()
def version() -> None:
    """Print the gaxis version."""
    typer.echo(__version__)


@app.command()
def config(as_json: bool = typer.Option(False, "--json")) -> None:
    """Show the effective configuration (file + environment)."""
    from ..config import config_path, load_config

    loaded = load_config()
    if as_json:
        _echo_json(json.loads(loaded.model_dump_json()))
        return
    typer.echo(f"file: {config_path() or '(defaults only)'}")
    typer.echo(
        f"confirmation: mode={loaded.confirmation.mode} "
        f"min_confidence={loaded.confirmation.min_confidence}"
    )
    typer.echo(
        f"render: preset={loaded.render.default_preset} "
        f"backend={loaded.render.default_backend} timeout={loaded.render.timeout_s:g}s"
    )
    typer.echo(f"ingest: mode={loaded.ingest.default_mode} network={loaded.ingest.allow_network}")
    typer.echo(f"knowledge: source={loaded.knowledge.source} retries={loaded.knowledge.retries}")


@app.command()
def presets(as_json: bool = typer.Option(False, "--json", help="machine-readable")) -> None:
    """List journal presets (geometry in mm, type in pt)."""
    rows = preset_table()
    if as_json:
        _echo_json(rows)
        return
    for row in rows:
        typer.echo(
            f"{row['name']:<20} {row['single_mm']:>10} mm  "
            f"double {row['double_mm']:>10} mm  {row['font_pt']} pt  "
            f"{row['dpi']} dpi  {row['label']}"
        )


@app.command()
def palettes(as_json: bool = typer.Option(False, "--json")) -> None:
    """List colour palettes, flagging colour-blind safety."""
    payload: list[dict[str, Any]] = [
        {
            "name": name,
            "colorblind_safe": PALETTES[name].colorblind_safe,
            "colors": PALETTES[name].colors,
            "description": PALETTES[name].description,
        }
        for name in palette_names()
    ]
    if as_json:
        _echo_json(payload)
        return
    for row in payload:
        flag = "cvd-safe  " if row["colorblind_safe"] else "cvd-risky "
        typer.echo(f"{row['name']:<12} {flag} {' '.join(row['colors'][:5])}  {row['description']}")


@app.command()
def tools(as_json: bool = typer.Option(True, "--json/--table")) -> None:
    """Print the frozen MCP tool contract (v2.2) with data classes."""
    catalog = service.tool_catalog()
    if as_json:
        _echo_json(catalog)
        return
    for spec in catalog:
        state = "ready" if spec["implemented"] else f"planned {spec['milestone']}"
        typer.echo(
            f"{spec['name']:<26} {spec['data_class']}  {spec['cost']:<6} "
            f"{state:<14} {spec['summary']}"
        )


@app.command()
def describe(
    data: Path = typer.Option(..., "--data", "-d", exists=True, dir_okay=False),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Profile a table and show the chart gaxis would default to."""
    try:
        result = service.describe(DescribeDataRequest(data_path=str(data.resolve())))
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(json.loads(result.model_dump_json()))
        return
    typer.echo(result.summary)
    spec = result.suggested_spec
    typer.echo(
        f"\nsuggested: {spec.chart_type.value}  x={spec.x}  y={spec.y}  hue={spec.hue}  "
        f"preset={spec.preset}"
    )


@app.command()
def plan(
    brief: str = typer.Argument(..., help="natural-language figure request"),
    preset: str | None = typer.Option(None, "--preset", "-p"),
    backend: str | None = typer.Option(None, "--backend"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Turn a figure brief into a plan (no data needed) — service flow 1, step 1."""
    try:
        result = service.plan_chart(
            PlanChartRequest(brief=brief, preset=preset, backend=backend)  # type: ignore[arg-type]
        )
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(json.loads(result.model_dump_json()))
        return
    chart = result.plan
    typer.echo(
        f"chart:    {chart.spec.chart_type.value}   preset: {chart.spec.preset}   "
        f"backend: {chart.spec.backend}   confidence: {chart.confidence:.2f}"
    )
    if chart.style_notes:
        typer.echo("style:")
        for note in chart.style_notes:
            typer.echo(f"  - {note}")
    typer.echo("columns:")
    for column in chart.required_columns:
        typer.echo(f"  - {column.role:<5} {column.kind:<11} {column.hint}")
    if chart.open_questions:
        typer.echo("ask the user:")
        for question in chart.open_questions:
            typer.echo(f"  ? {question}")
    if result.message:
        typer.echo(f"note: {result.message}")


@app.command()
def ingest(
    source: str = typer.Argument(..., help="PDF path, DOI, arXiv id, PubMed/PMC id, or a PDF URL"),
    mode: str | None = typer.Option(None, "--mode", help="kb_first | full (default from config)"),
    min_quality: float = typer.Option(0.0, "--min-quality"),
    no_code: bool = typer.Option(False, "--no-code", help="skip repository discovery"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Service flow 2: parse a paper into figure manifests (PDF today)."""
    try:
        selected_mode = mode if mode in {"kb_first", "full"} else None
        result = service.ingest_paper(
            IngestPaperRequest(
                source=source,
                mode=selected_mode,  # type: ignore[arg-type]
                min_quality=min_quality,
                with_code=False if no_code else None,
            )
        )
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(json.loads(result.model_dump_json()))
        return
    typer.echo(f"paper:  {result.paper_id or '-'}  {result.title or ''}")
    typer.echo(f"source: {result.source_kind}  mode={result.mode}  charts={result.charts_found}")
    for brief in result.figure_briefs:
        kind = brief.chart_type_guess.value if brief.chart_type_guess else "?"
        typer.echo(f"  {brief.figure_ref:<8} {kind:<12} {brief.caption[:80]}")
    for manifest_id in result.manifest_ids:
        typer.echo(f"  manifest: {manifest_id}")
    if result.message:
        typer.echo(f"note: {result.message}")


@app.command("manifest")
def manifest_cmd(
    manifest_id: str = typer.Argument(...),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one ChartReproManifest (by id) or a rendered figure manifest (by path)."""
    candidate = Path(manifest_id)
    if candidate.is_file():
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        if "figure_id" in payload:
            if as_json:
                _echo_json(payload)
                return
            typer.echo(f"{payload['figure_id']}  {payload.get('backend', '')}")
            typer.echo(f"  preset:  {payload.get('preset', '-')}")
            typer.echo(f"  code:    {payload.get('code_path', '-')}")
            typer.echo(f"  data:    {payload.get('data', {}).get('sha256', '-')[:12]}")
            typer.echo(f"  code sha:{str(payload.get('code_sha256', ''))[:12]}")
            typer.echo(f"  source:  {payload.get('source', '-')}")
            typer.echo(f"  lint:    {'clean' if payload.get('lint', {}).get('ok') else 'issues'}")
            return
        manifest_id = str(payload.get("manifest_id") or manifest_id)
    result = service.get_chart_manifest(GetChartManifestRequest(manifest_id=manifest_id))
    if not result.found or result.manifest is None:
        typer.echo(result.message or "not found", err=True)
        raise typer.Exit(code=1)
    if as_json:
        _echo_json(result.manifest)
        return
    payload = result.manifest
    typer.echo(f"{payload['manifest_id']}  {payload.get('figure_ref', '')}")
    typer.echo(f"  title:   {payload.get('paper_title') or '-'}")
    typer.echo(f"  file:    {payload['chart_file']}")
    quality = payload["chart_quality_score"]
    level = payload["reproduction"]["level"]
    typer.echo(f"  quality: {quality}  level: {level}")
    typer.echo(f"  caption: {payload['caption'][:200]}")
    if payload.get("citing_paragraph"):
        typer.echo(f"  citing:  {payload['citing_paragraph'][:200]}")


kb_app = typer.Typer(help="Knowledge base (gbrain paper-kb): status, ingest, search")
app.add_typer(kb_app, name="kb")


@kb_app.command("adopt")
def kb_adopt(
    manifest_id: str = typer.Argument(..., help="paper figure manifest id"),
    code: Path | None = typer.Option(
        None, "--code", help="local script (defaults to the candidate)"
    ),
    preset: str = typer.Option("default", "--preset", "-p"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Register a reproduced paper script as an adaptable template (explicit contract)."""
    try:
        adopted = service.adopt_chart_asset(manifest_id, code_path=code, preset=preset)
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(adopted.__dict__)
        return
    typer.echo(f"asset:     {adopted.slug}")
    typer.echo(f"interface: {adopted.interface}")
    typer.echo(f"code:      {adopted.code_path}")
    typer.echo(f"sha256:    {adopted.code_sha256}")


@kb_app.command("seed")
def kb_seed(
    preset: list[str] = typer.Option(None, "--preset", "-p", help="limit to these presets"),
    backend: list[str] = typer.Option(None, "--backend", help="python and/or r"),
    force: bool = typer.Option(
        False, "--force", help="rewrite pages even if the code hash matches"
    ),
) -> None:
    """Seed the KB with verified builtin templates (idempotent, no network)."""
    kb = service.knowledge()
    if kb is None:
        typer.echo("knowledge base disabled: set [knowledge] enabled = true", err=True)
        raise typer.Exit(code=1)
    backends = tuple(backend) if backend else ("python", "r")
    from ..config import settings
    from ..kb.templates import seed_templates

    summary = seed_templates(
        kb,
        data_root=settings().data_root,
        presets=preset or None,
        backends=backends,
        force=force,
        progress=lambda slug: typer.echo(f"  wrote {slug}"),
    )
    typer.echo(
        f"templates: {len(summary.written)} written, {len(summary.skipped)} unchanged, "
        f"{len(summary.failed)} failed"
    )
    for slug, error in summary.failed:
        typer.echo(f"  failed {slug}: {error}", err=True)
    if summary.failed:
        raise typer.Exit(code=1)


@kb_app.command("status")
def kb_status_cmd(as_json: bool = typer.Option(False, "--json")) -> None:
    """Is the knowledge base reachable, and how full is it?"""
    status = service.kb_status()
    if as_json:
        _echo_json(
            {
                "available": status.available,
                "source": status.source,
                "pages": status.pages,
                "missing_embeddings": status.missing_embeddings,
                "message": status.message,
            }
        )
        return
    typer.echo(f"source:  {status.source}   available={status.available}")
    typer.echo(f"pages:   {status.pages}   missing_embeddings={status.missing_embeddings}")
    if status.message:
        typer.echo(f"note:    {status.message}")


@kb_app.command("ingest")
def kb_ingest_cmd(
    force: bool = typer.Option(False, "--force", help="re-write pages even when unchanged"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Ingest every manifest on disk into the knowledge base (idempotent)."""
    summary = service.kb_ingest(force=force)
    if as_json:
        _echo_json(summary.as_dict())
        return
    typer.echo(summary.message())
    for asset in summary.upserted:
        typer.echo(f"  upserted: {asset}")
    for asset, error in summary.failed:
        typer.echo(f"  failed:   {asset}: {error}")


@kb_app.command("search")
def kb_search_cmd(
    query: str = typer.Argument("", help="free-text intent; may be omitted with --schema"),
    k: int = typer.Option(5, "--k"),
    chart: str | None = typer.Option(None, "--chart"),
    min_level: str | None = typer.Option(None, "--min-level"),
    image: Path | None = typer.Option(
        None, "--image", help="rank by perceptual similarity to this figure"
    ),
    schema: Path | None = typer.Option(
        None, "--schema", help="search by table shape instead of text"
    ),
    tier: str | None = typer.Option(None, "--tier", help="gold | dense | reject"),
    has_code: bool | None = typer.Option(
        None, "--has-code/--no-code", help="require (or exclude) recorded code"
    ),
    sheet: bool = typer.Option(False, "--sheet", help="write a contact sheet of the candidates"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Search the paper knowledge base for reusable figure assets."""
    result = service.search_chart_assets(
        SearchChartAssetsRequest(
            query=query,
            query_image_path=str(image) if image else None,
            schema_path=str(schema) if schema else None,
            k=k,
            chart_type=chart,  # type: ignore[arg-type]
            min_reproduction_level=min_level,  # type: ignore[arg-type]
            design_tier=tier,  # type: ignore[arg-type]
            has_code=has_code,
            render_sheet=sheet,
        )
    )
    if as_json:
        _echo_json(json.loads(result.model_dump_json()))
        return
    typer.echo(f"{result.total} hit(s)  degraded={result.degraded}  {result.message}")
    if result.sheet_path:
        typer.echo(f"sheet: {result.sheet_path}")
    for asset in result.assets:
        kind = asset.chart_type.value if asset.chart_type else "?"
        extra = ""
        if asset.image_similarity is not None:
            extra = f" img={asset.image_similarity:.2f}"
        typer.echo(
            f"  {asset.asset_id:<28} {kind:<12} {asset.reproduction_level or '-':<3} "
            f"sim={asset.visual_similarity if asset.visual_similarity is not None else '-'}{extra}"
        )


design_app = typer.Typer(
    help="Design quality: judge figures against the aesthetic/visualization rubric"
)
app.add_typer(design_app, name="design")


@design_app.command("candidates")
def design_candidates(
    directory: Path = typer.Argument(..., exists=True, file_okay=False),
    out: Path | None = typer.Option(None, "--out"),
    limit: int = typer.Option(40, "--limit"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Numbered sheet + contact sheet for exemplar figures (golden-set curation)."""
    from ..design import build_candidate_sheet

    images = sorted(
        path
        for path in directory.iterdir()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
    )
    if not images:
        _fail(GaxisError("no_images", f"no images found in {directory}"))
        return
    target = out or (directory / "candidates")
    sheet, csv, contact = build_candidate_sheet(images, out_dir=target, limit=limit)
    if as_json:
        _echo_json({"sheet": str(sheet), "csv": str(csv), "contact_sheet": str(contact)})
        return
    typer.echo(f"candidates: {len(images)} image(s)")
    typer.echo(f"sheet:   {sheet}")
    typer.echo(f"csv:     {csv}")
    typer.echo(f"contact: {contact}")


@design_app.command("judge-dir")
def design_judge_dir(
    directory: Path = typer.Argument(..., exists=True, file_okay=False),
    out: Path | None = typer.Option(None, "--out"),
    limit: int = typer.Option(500, "--limit"),
    workers: int = typer.Option(4, "--workers"),
    unique: bool = typer.Option(True, "--unique/--all", help="skip byte-identical duplicates"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Judge every image in a folder and write a ranked CSV (golden-set calibration)."""
    from ..design import judge_directory
    from ..design_judge import build_judge

    candidates = sorted(
        path
        for path in directory.rglob("*")
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    if unique:
        import hashlib

        seen: set[str] = set()
        images: list[Path] = []
        for path in candidates:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            images.append(path)
    else:
        images = candidates
    images = images[:limit]
    if not images:
        _fail(GaxisError("no_images", f"no images found under {directory}"))
        return
    judge = build_judge(service.settings())
    target = out or (directory / "judged")
    typer.echo(f"judge: {judge.name}   images: {len(images)}   workers: {workers}")
    json_path, csv_path = judge_directory(images, judge=judge, out_dir=target, workers=workers)
    if as_json:
        _echo_json({"judgements": str(json_path), "csv": str(csv_path)})
        return
    typer.echo(f"judgements: {json_path}")
    typer.echo(f"csv:        {csv_path}")


@design_app.command("judge")
def design_judge_cmd(
    image: Path = typer.Argument(..., exists=True, dir_okay=False),
    caption: str = typer.Option("", "--caption"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Judge one figure with the configured design judge (vision model or objective)."""
    from ..design_judge import DesignJudgeError, build_judge

    judge = build_judge(service.settings())
    try:
        quality = judge.judge(image, caption=caption)
    except DesignJudgeError as exc:
        _fail(GaxisError("judge_failed", str(exc)))
        return
    if as_json:
        _echo_json(json.loads(quality.model_dump_json()))
        return
    typer.echo(f"judge:  {quality.method}")
    typer.echo(
        "aesthetic: " + ("not judged" if quality.aesthetic is None else f"{quality.aesthetic:.2f}")
    )
    typer.echo(f"visualization: {quality.visualization:.2f}")
    for note in quality.notes:
        typer.echo(f"  - {note}")


quality_app = typer.Typer(help="Extraction quality: build a ranking sheet, calibrate weights")
app.add_typer(quality_app, name="quality")


@quality_app.command("sheet")
def quality_sheet_cmd(
    out: Path | None = typer.Option(None, "--out", help="output directory"),
    limit: int = typer.Option(30, "--limit"),
    force: bool = typer.Option(False, "--force", help="overwrite a sheet that already has ranks"),
    sort_by: str = typer.Option("design", "--sort", help="design | extraction"),
    min_design: float = typer.Option(
        0.0, "--min-design", help="drop figures below this design score"
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Write a human-ranking sheet (Markdown + contact sheet) for the current manifests."""
    try:
        sheet, contact = service.quality_sheet(
            out_dir=out,
            limit=limit,
            force=force,
            sort_by=sort_by,
            min_design=min_design,
        )
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json({"sheet": str(sheet), "contact_sheet": str(contact) if contact else None})
        return
    typer.echo(f"sheet:   {sheet}")
    if contact:
        typer.echo(f"contact: {contact}")
    typer.echo("rank 1..N in sheet.md, then: gaxis quality calibrate rankings.csv")


@quality_app.command("backfill")
def quality_backfill_cmd(
    workers: int = typer.Option(4, "--workers"),
    force: bool = typer.Option(False, "--force", help="re-judge even vision-scored figures"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Recompute crop quality + design for manifests created before those components existed."""
    result = service.quality_backfill(workers=workers, force=force)
    if as_json:
        _echo_json(result)
        return
    typer.echo(
        f"updated {result['updated']} manifest(s), skipped {result['skipped']} "
        "(no artwork or unreadable)"
    )


@quality_app.command("calibrate")
def quality_calibrate_cmd(
    rankings: Path = typer.Argument(..., exists=True, dir_okay=False),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Fit quality weights to a human ranking (CSV: manifest_id,human_rank)."""
    import csv

    rows: list[tuple[str, int]] = []
    try:
        if rankings.suffix.lower() in {".md", ".markdown"}:
            from ..quality import parse_sheet_ranks

            rows = parse_sheet_ranks(rankings.read_text(encoding="utf-8"))
            if not rows:
                _fail(
                    GaxisError(
                        "bad_rankings",
                        "no filled-in ranks found in the sheet",
                        hint="put 1..N in the last column of sheet.md, or use a CSV",
                    )
                )
                return
        else:
            with rankings.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                id_field = "manifest_id" if "manifest_id" in (reader.fieldnames or []) else "id"
                rank_field = "human_rank" if "human_rank" in (reader.fieldnames or []) else "rank"
                for row in reader:
                    identifier = (row.get(id_field) or "").strip()
                    raw_rank = (row.get(rank_field) or "").strip()
                    if not identifier or not raw_rank:
                        continue
                    rows.append((identifier, int(raw_rank)))
    except (OSError, ValueError) as exc:
        _fail(GaxisError("bad_rankings", f"cannot read rankings: {exc}"))
        return
    try:
        report = service.quality_calibrate(rows)
    except GaxisError as exc:
        _fail(exc)
        return
    import json as _json

    report_path = rankings.parent / "calibration-report.json"
    report_path.write_text(_json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8")
    if as_json:
        _echo_json(report.as_dict())
        return
    typer.echo(f"samples:  {report.samples}")
    typer.echo(f"baseline: Spearman {report.baseline_spearman:.3f}")
    typer.echo(f"best:     Spearman {report.best_spearman:.3f}")
    typer.echo(
        f"tiers:    {report.distinct_scores} distinct score level(s); "
        f"varying components: {', '.join(report.varying_components) or 'none'}"
    )
    typer.echo(f"ceiling:  Spearman {report.ceiling_spearman:.3f} given those tiers")
    if not report.improved:
        typer.echo("note: reweighting cannot improve the fit - the signal is not in the components")
    typer.echo("component Spearman:")
    for name, value in report.component_spearman.items():
        typer.echo(f"  {name:<11} {value:+.3f}")
    typer.echo("\nsuggested [quality] block:")
    typer.echo(report.toml_snippet())
    typer.echo(f"report:   {report_path}")


@app.command()
def reproduce(
    manifest_id: str = typer.Argument(...),
    code: Path = typer.Option(..., "--code", exists=True, dir_okay=False, help="script to run"),
    data: Path | None = typer.Option(None, "--data", help="optional input data (mounted at /data)"),
    engine: str | None = typer.Option(
        None, "--engine", help="podman | local (default from config)"
    ),
    timeout: float = typer.Option(300.0, "--timeout"),
    allow_network: bool = typer.Option(False, "--allow-network"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Service flow 2: run a figure script in the sandbox and grade the reproduction."""
    try:
        result = service.reproduce_chart_code(
            ReproduceChartCodeRequest(
                manifest_id=manifest_id,
                code_path=str(code),
                data_path=str(data) if data else None,
                timeout_s=timeout,
                allow_network=allow_network,
                engine=engine,  # type: ignore[arg-type]
            )
        )
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(json.loads(result.model_dump_json()))
        return
    typer.echo(f"manifest: {result.manifest_id}")
    typer.echo(f"engine:   {result.engine}   run: {result.run_status}   level: {result.level}")
    if result.visual_similarity is not None:
        typer.echo(f"similarity: {result.visual_similarity:.3f}")
    for output in result.outputs:
        typer.echo(f"  rendered: {output.path}")
    if result.failure_reason:
        typer.echo(f"reason:   {result.failure_reason[:300]}")


@app.command("render")
def render_cmd(
    data: Path = typer.Option(..., "--data", "-d", exists=True, dir_okay=False),
    chart: ChartType | None = typer.Option(None, "--chart", "-c", case_sensitive=False),
    x: str | None = typer.Option(None, "--x"),
    y: str | None = typer.Option(None, "--y"),
    hue: str | None = typer.Option(None, "--hue"),
    yerr: str | None = typer.Option(None, "--yerr"),
    weight: str | None = typer.Option(None, "--weight", help="edge weight column (network)"),
    backend: str = typer.Option("python", "--backend", help="python (matplotlib) or r (ggplot2)"),
    preset: str = typer.Option("default", "--preset", "-p"),
    palette: str | None = typer.Option(None, "--palette"),
    width: float | None = typer.Option(None, "--width", help="width in mm"),
    height: float | None = typer.Option(None, "--height", help="height in mm"),
    dpi: int = typer.Option(600, "--dpi"),
    formats: str = typer.Option("pdf,png", "--formats", help="comma separated: pdf,svg,png,tiff"),
    annotate: bool = typer.Option(False, "--annotate", help="print values on the marks"),
    title: str | None = typer.Option(None, "--title"),
    xlabel: str | None = typer.Option(None, "--xlabel"),
    ylabel: str | None = typer.Option(None, "--ylabel"),
    out: Path | None = typer.Option(None, "--out", help="output root directory"),
    source_asset: str | None = typer.Option(
        None, "--source-asset", help="KB asset this figure follows (recorded as feedback)"
    ),
    allow_lint_errors: bool = typer.Option(False, "--allow-lint-errors"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Render a figure from data and keep the script that produced it."""
    request = RenderRequest(
        data_path=str(data.resolve()),
        chart_type=chart,
        x=x,
        y=y,
        hue=hue,
        yerr=yerr,
        weight=weight,
        preset=preset,
        palette=palette,
        backend=backend,  # type: ignore[arg-type]
        width_mm=width,
        height_mm=height,
        dpi=dpi,
        formats=[f.strip() for f in formats.split(",") if f.strip()],
        annotate_values=annotate,
        title=title,
        xlabel=xlabel,
        ylabel=ylabel,
        out_dir=str(out) if out else None,
        source_asset=source_asset,
    )
    try:
        result = render(request)
    except GaxisError as exc:
        _fail(exc)
        return
    except KeyError as exc:
        _fail(GaxisError("bad_parameter", str(exc)))
        return
    if as_json:
        _echo_json(json.loads(result.model_dump_json()))
    else:
        typer.echo(f"figure: {result.figure_id}")
        typer.echo(f"dir:    {Path(result.manifest_path).parent}")
        typer.echo(f"code:   {result.code_path}")
        for output in result.outputs:
            geometry = ""
            if output.width_mm and output.height_mm:
                geometry = f" ({output.width_mm:.1f}x{output.height_mm:.1f} mm"
                geometry += f" @{output.dpi} dpi)" if output.dpi else ")"
            typer.echo(f"wrote:  {output.path}{geometry}")
        typer.echo(result.lint.format_text())
    if not result.lint.ok and not allow_lint_errors:
        raise typer.Exit(code=3)


ops_app = typer.Typer(help="Ingestion queue: checkpointed paper crawling")
app.add_typer(ops_app, name="ops")


def _queue_path() -> Path:
    from ..config import settings

    return settings().data_root / "ops" / "queue.db"


@ops_app.command("enqueue")
def ops_enqueue(
    sources: list[str] = typer.Argument(..., help="DOI, arXiv id, PubMed id, PDF path or paper id"),
    mode: str = typer.Option("full", "--mode"),
    kind: str = typer.Option("ingest", "--kind", help="ingest | reproduce"),
) -> None:
    """Add sources to the queue (duplicates are ignored)."""
    from ..ops.state import JobQueue

    queue = JobQueue(_queue_path())
    added = queue.enqueue(sources, mode=mode, kind=kind)
    queue.close()
    typer.echo(f"enqueued {added} new source(s) — {len(sources) - added} already known")


@ops_app.command("run")
def ops_run(
    limit: int = typer.Option(5, "--limit"),
    retries: int = typer.Option(2, "--retries"),
    stall_minutes: int = typer.Option(30, "--stall-minutes"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Process pending sources; each one is checkpointed in the queue."""
    from ..ops.runner import run_queue
    from ..ops.state import JobQueue

    queue = JobQueue(_queue_path())
    summary = run_queue(queue, limit=limit, retries=retries, stall_minutes=stall_minutes)
    state = queue.status()
    queue.close()
    if as_json:
        _echo_json({"run": summary.as_dict(), "queue": state})
        return
    typer.echo(
        f"processed {len(summary.processed)}, failed {len(summary.failed)}, "
        f"reclaimed {summary.reclaimed}"
    )
    for source in summary.processed:
        typer.echo(f"  done: {source}")
    for source, error in summary.failed:
        typer.echo(f"  failed: {source}: {error}")
    typer.echo("queue: " + ", ".join(f"{key}={value}" for key, value in sorted(state.items())))


@ops_app.command("verify")
def ops_verify(
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Check that every `done` job still has its manifests; requeue what is gone."""
    from ..config import settings
    from ..ops.runner import verify_queue
    from ..ops.state import JobQueue

    queue = JobQueue(_queue_path())
    summary = verify_queue(queue, settings().manifests_dir)
    queue.close()
    if as_json:
        _echo_json(summary.as_dict())
        return
    typer.echo(
        f"checked {summary.checked} done job(s); missing {summary.missing} manifest(s); "
        f"requeued {len(summary.requeued)}"
    )
    for source in summary.requeued:
        typer.echo(f"  requeued: {source}")


@ops_app.command("status")
def ops_status(
    reset: str | None = typer.Option(None, "--reset", help="requeue one source, or 'all'"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show the queue, optionally requeueing failed jobs."""
    from ..ops.state import JobQueue

    queue = JobQueue(_queue_path())
    if reset:
        count = queue.reset(None if reset == "all" else reset)
        typer.echo(f"requeued {count} job(s)")
    jobs = queue.jobs()
    state = queue.status()
    queue.close()
    if as_json:
        _echo_json({"status": state, "jobs": [job.__dict__ for job in jobs]})
        return
    typer.echo("status: " + ", ".join(f"{key}={value}" for key, value in sorted(state.items())))
    heartbeat = _queue_path().parent / "heartbeat.json"
    if heartbeat.is_file():
        payload = json.loads(heartbeat.read_text(encoding="utf-8"))
        typer.echo(
            f"last run: {payload.get('finished_at')} "
            f"({len(payload.get('processed', []))} processed, {payload.get('duration_s')} s)"
        )
    for job in jobs[:20]:
        typer.echo(
            f"  {job.status:<8} attempts={job.attempts} {job.source}"
            + (f"  [{job.last_error}]" if job.last_error else "")
        )


@app.command()
def adapt(
    data: Path = typer.Option(..., "--data", "-d"),
    query: str | None = typer.Option(
        None, "--query", "-q", help="figure intent, e.g. 'grouped bar'"
    ),
    asset_id: str | None = typer.Option(None, "--asset", help="template asset slug"),
    preset: str = typer.Option("default", "--preset", "-p"),
    backend: str = typer.Option("python", "--backend"),
    out: Path | None = typer.Option(None, "--out"),
    dry_run: bool = typer.Option(False, "--dry-run", help="emit adapted code without running it"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Adapt a verified KB template to local data (same script skeleton, new bindings)."""
    try:
        result = service.adapt_chart_code(
            service.AdaptChartCodeRequest(
                data_path=str(data),
                query=query,
                asset_id=asset_id,
                preset=preset,
                backend=backend,  # type: ignore[arg-type]
                dry_run=dry_run,
            )
        )
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(json.loads(result.model_dump_json()))
        return
    typer.echo(f"source:  {result.source}")
    if result.asset_ids:
        typer.echo(f"asset:   {result.asset_ids[0]}")
    if result.fallback_reason:
        typer.echo(f"fallback: {result.fallback_reason}")
    typer.echo(f"figure:  {result.figure_id}")
    typer.echo(f"code:    {result.code_path}")
    for output in result.outputs:
        typer.echo(f"wrote:   {output.path}")
    typer.echo(result.lint.format_text())


analysis_app = typer.Typer(help="Analysis recipes: table -> table steps for figures")
app.add_typer(analysis_app, name="analysis")


@analysis_app.command("list")
def analysis_list(as_json: bool = typer.Option(False, "--json")) -> None:
    """List analysis recipes (input contract, outputs, provenance)."""
    recipes = service.analysis_recipes()
    if as_json:
        _echo_json(recipes)
        return
    for recipe in recipes:
        typer.echo(f"{recipe['id']}: {recipe['title']}")
        typer.echo(f"  input:   {recipe['input']}")
        typer.echo(f"  outputs: {', '.join(recipe['outputs'])}")
        typer.echo(f"  note:    {recipe['note']}")


@analysis_app.command("workflows")
def analysis_workflows_cmd(as_json: bool = typer.Option(False, "--json")) -> None:
    """List Snakemake workflow recipes (scaffold + validate; bacmap runs them)."""
    workflows = service.analysis_workflows()
    if as_json:
        _echo_json(workflows)
        return
    for workflow in workflows:
        typer.echo(f"{workflow['id']} ({workflow['version']}): {workflow['note']}")
        typer.echo(f"  inputs:  {', '.join(workflow['inputs'])}")
        typer.echo(f"  outputs: {', '.join(workflow['outputs'])}")
        typer.echo(f"  tools:   {', '.join(workflow['tools'])}")


@analysis_app.command("scaffold")
def analysis_scaffold_cmd(
    workflow: str = typer.Argument(..., help="workflow id, e.g. snp-tree"),
    out: Path = typer.Option(..., "--out", help="project directory"),
    alignment: Path = typer.Option(..., "--alignment", help="FASTA alignment"),
    metadata: Path | None = typer.Option(None, "--metadata"),
    model: str = typer.Option("GTR+G", "--model"),
    bootstrap: int = typer.Option(1000, "--bootstrap"),
    threads: int = typer.Option(4, "--threads"),
    seed: int = typer.Option(42, "--seed"),
    container: str = typer.Option(
        "", "--container", help="pinned IQ-TREE image (digest preferred)"
    ),
    check: bool = typer.Option(False, "--check", help="validate with `snakemake -n`"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Generate a Snakemake project for an analysis gaxis does not execute itself."""
    try:
        scaffold, output = service.analysis_scaffold(
            workflow,
            out_dir=out,
            alignment=alignment,
            metadata=metadata,
            model=model,
            bootstrap=bootstrap,
            threads=threads,
            seed=seed,
            container=container,
            check=check,
        )
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(json.loads(scaffold.model_dump_json()))
        return
    typer.echo(f"workflow: {scaffold.workflow_id} ({scaffold.version})")
    typer.echo(f"out:      {scaffold.out_dir}")
    typer.echo(f"files:    {', '.join(scaffold.files)}")
    typer.echo(f"container:{scaffold.container or ' (not set; pin one before running)'}")
    typer.echo(f"run:      cd {scaffold.out_dir} && snakemake --cores {threads}")
    if output:
        typer.echo("check:    OK")
        typer.echo(output.splitlines()[-6:] and "\n".join(output.splitlines()[-6:]))


@analysis_app.command("check")
def analysis_check_cmd(
    directory: Path = typer.Argument(..., help="workflow project directory"),
) -> None:
    """Validate a workflow project with `snakemake -n`."""
    try:
        output = service.check_workflow(directory)
    except GaxisError as exc:
        _fail(exc)
        return
    typer.echo("workflow OK")
    typer.echo("\n".join(output.splitlines()[-8:]))


@analysis_app.command("run")
def analysis_run_cmd(
    recipe: str = typer.Argument(..., help="recipe id, e.g. amr-cooccurrence"),
    input: Path = typer.Option(..., "--input", "-i", help="long table: sample,gene[,gene_class]"),
    out: Path | None = typer.Option(None, "--out"),
    min_prevalence: float = typer.Option(0.05, "--min-prevalence"),
    min_support: int = typer.Option(2, "--min-support"),
    weight: str = typer.Option("jaccard", "--weight", help="jaccard | count"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run an analysis recipe on a user table (no bioinformatics re-computation)."""
    from ..models.analysis import AmrCooccurrenceParams

    try:
        run = service.analysis_run(
            recipe,
            input_path=input,
            out_dir=out,
            params=AmrCooccurrenceParams(
                min_prevalence=min_prevalence,
                min_support=min_support,
                weight=weight,  # type: ignore[arg-type]
            ),
        )
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(json.loads(run.model_dump_json()))
        return
    typer.echo(f"run:     {run.run_id}")
    typer.echo(f"recipe:  {run.recipe}")
    typer.echo(f"samples: {run.samples}   genes: {run.genes}   edges: {run.edges}")
    typer.echo(f"nodes:   {run.outputs['nodes']}")
    typer.echo(f"edges:   {run.outputs['edges']}")
    typer.echo(
        "next:    gaxis render --chart network --data "
        f"{run.outputs['edges']} --x source --y target --weight weight"
    )


@app.command("reconstruct")
def reconstruct_cmd(
    manifest_id: str = typer.Argument(..., help="paper figure manifest id"),
    data: Path | None = typer.Option(None, "--data", help="optional input table"),
    engine: str | None = typer.Option(None, "--engine", help="podman | local"),
    rounds: int | None = typer.Option(None, "--rounds", help="generate/fix rounds"),
    target: float | None = typer.Option(None, "--target", help="stop at this similarity"),
    repair: bool = typer.Option(
        False, "--repair", help="start from the author's script and let the model fix it"
    ),
    model: str | None = typer.Option(None, "--model", help="override the configured model"),
    timeout: float | None = typer.Option(None, "--timeout", help="per-request timeout (s)"),
    max_side: int | None = typer.Option(
        None, "--max-side", help="image long side sent to the model"
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """LLM writes (or repairs) figure code; the sandbox grades it against the paper image."""
    try:
        result = service.reconstruct_chart(
            manifest_id,
            data_path=data,
            engine=engine,
            rounds=rounds,
            target=target,
            repair=repair,
            model=model,
            timeout_s=timeout,
            max_side=max_side,
        )
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(json.loads(result.model_dump_json()))
        return
    typer.echo(f"manifest: {result.manifest_id}")
    typer.echo(f"method:   {result.method}   model: {result.model}   rounds: {result.rounds}")
    typer.echo(f"engine:   {result.engine}   level: {result.level}")
    if result.visual_similarity is not None:
        history = ", ".join(f"{value:.3f}" for value in result.similarity_history)
        typer.echo(f"similarity: {result.visual_similarity:.3f}   history: [{history}]")
    typer.echo(f"code:     {result.code_path}")
    if result.data_path:
        typer.echo(f"data:     {result.data_path} ({result.data_source})")
    if result.failure_reason:
        typer.echo(f"note:     {result.failure_reason}")
    if result.kb_refresh:
        typer.echo(f"kb:       {result.kb_refresh}")


@app.command("reproduce-paper")
def reproduce_paper_cmd(
    paper_id: str = typer.Argument(..., help="paper id, e.g. pdf-<sha8>"),
    data: Path | None = typer.Option(None, "--data", help="input table shared by the figures"),
    min_confidence: float = typer.Option(0.5, "--min-confidence"),
    limit: int = typer.Option(8, "--limit"),
    engine: str | None = typer.Option(None, "--engine", help="podman | local"),
    synthetic: bool = typer.Option(
        False,
        "--synthetic",
        help="generate labelled synthetic input when the paper's data is absent",
    ),
    force: bool = typer.Option(False, "--force", help="re-run figures already graded L1/L2"),
    reconstruct_missing: bool = typer.Option(
        False,
        "--reconstruct-missing",
        help="LLM-reconstruct figures whose author code is missing or does not run",
    ),
    rounds: int | None = typer.Option(
        None, "--rounds", help="reconstruction rounds (default from config)"
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Reproduce every suitable figure of one ingested paper."""
    from ..config import settings
    from ..repro.batch import reproduce_paper

    try:
        summary = reproduce_paper(
            paper_id,
            manifests_dir=settings().manifests_dir,
            data_path=data,
            min_confidence=min_confidence,
            limit=limit,
            engine=engine,
            synthetic=synthetic,
            force=force,
            reconstruct=reconstruct_missing,
            reconstruct_rounds=rounds,
        )
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(summary.as_dict())
        return
    raw_counts = summary.as_dict()["counts"]
    counts = raw_counts if isinstance(raw_counts, dict) else {}
    typer.echo(
        f"{paper_id}: " + ", ".join(f"{key}={value}" for key, value in counts.items() if value)
    )
    for item in summary.items:
        detail = f" ({item.level})" if item.level != "none" else ""
        note = f"  [{item.reason}]" if item.reason else ""
        typer.echo(f"  {item.status:<11} {item.manifest_id}{detail}{note}")


@app.command()
def compose(
    panels: str = typer.Option(
        ..., "--panels", help="comma separated figure ids or manifest paths"
    ),
    layout: str | None = typer.Option(None, "--layout", help="ROWSxCOLS, e.g. 2x2"),
    preset: str = typer.Option("default", "--preset", "-p"),
    width: float | None = typer.Option(None, "--width", help="page width in mm"),
    height: float | None = typer.Option(None, "--height", help="page height in mm"),
    no_labels: bool = typer.Option(False, "--no-labels", help="skip A/B/C panel letters"),
    uniform: bool = typer.Option(
        False, "--uniform", help="re-render panels at the composition preset and cell size"
    ),
    out: Path | None = typer.Option(None, "--out"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Compose already-rendered panels into one publication page (vector, no re-render)."""
    identifiers = [part.strip() for part in panels.split(",") if part.strip()]
    grid: tuple[int, int] | None = None
    if layout:
        try:
            rows_text, cols_text = layout.lower().split("x", 1)
            grid = (int(rows_text), int(cols_text))
        except ValueError:
            _fail(GaxisError("bad_layout", f"expected ROWSxCOLS, got {layout!r}"))
            return
    try:
        manifest = service.compose(
            identifiers,
            preset=preset,
            out_dir=out,
            layout=grid,
            width_mm=width,
            height_mm=height,
            labels=not no_labels,
            uniform=uniform,
        )
    except GaxisError as exc:
        _fail(exc)
        return
    if as_json:
        _echo_json(json.loads(manifest.model_dump_json()))
        return
    typer.echo(f"composition: {manifest.composition_id}")
    rows, cols = manifest.layout
    typer.echo(f"layout:      {rows}x{cols}  {manifest.width_mm}x{manifest.height_mm} mm")
    typer.echo(f"pdf:         {manifest.output_pdf}")
    if manifest.output_png:
        typer.echo(f"png:         {manifest.output_png}")
    for panel in manifest.panels:
        typer.echo(f"  {panel.label or '-':<2} {panel.manifest_id}")
    typer.echo(manifest.lint.format_text())


@app.command()
def lint(
    paths: list[Path] = typer.Argument(..., help="rendered files (pdf/svg/png)"),
    preset: str = typer.Option("default", "--preset", "-p"),
    width: float | None = typer.Option(None, "--width", help="expected width in mm"),
    height: float | None = typer.Option(None, "--height", help="expected height in mm"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Check finished figures against a journal preset (language independent)."""
    try:
        report = lint_files(paths, preset_name=preset, width_mm=width, height_mm=height)
    except KeyError as exc:
        _fail(GaxisError("bad_parameter", str(exc)))
        return
    if as_json:
        _echo_json(json.loads(report.model_dump_json()))
    else:
        typer.echo(report.format_text())
    if not report.ok:
        raise typer.Exit(code=3)


@app.command()
def health(as_json: bool = typer.Option(False, "--json")) -> None:
    """Read-only probe: backends, presets, stage readiness."""
    status = service.health()
    if as_json:
        _echo_json(json.loads(status.model_dump_json()))
        return
    typer.echo(f"gaxis {status.version}  ok={status.ok}  data_root={status.data_root}")
    typer.echo(f"backends: matplotlib={status.python_backend}  Rscript={status.r_backend}")
    for name, state in status.stages.items():
        typer.echo(f"  {name:<26} {state}")


if __name__ == "__main__":  # pragma: no cover
    app()
