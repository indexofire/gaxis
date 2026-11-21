"""MCP server for gaxis: ten tools over contract v2.1 (ADR-02, ADR-05, ADR-14).

Run it as a production service:

    GAXIS_MCP_TOKEN=$(openssl rand -hex 24) gaxis-mcp --transport http --port 8770

stdio exists for local debugging only; hosts use Streamable HTTP.

Error convention: a failed call returns ``{"code", "message", "hint"?}`` with a
stable code instead of raising, so a host such as bacmap can branch on it.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from .. import __version__, service
from ..errors import GaxisError
from ..models.tools import (
    AdaptChartCodeRequest,
    DescribeDataRequest,
    GetChartManifestRequest,
    IngestPaperRequest,
    PlanChartRequest,
    RenderRequest,
    ReproduceChartCodeRequest,
    SearchChartAssetsRequest,
)

INSTRUCTIONS = """\
gaxis renders publication-grade figures from tidy tables and returns the exact
script that produced them.

Recommended flow:
1. `describe_data_schema` — profile the table, get a suggested spec.
2. `render_chart_from_data` — override any field of the spec and render; keep the
   returned `code_path` and `manifest_path` as the deliverable.
3. `search_chart_assets` / `adapt_chart_code` — knowledge-base path (paper figure
   templates). Until M4 these degrade to builtin templates with a `fallback_reason`.

Every figure is linted against a journal preset (path lengths in mm, fonts in pt,
vector output, colour-blind safety). Lint findings are returned, never suppressed.
`health` is read-only and safe to poll.
"""


def _error(exc: GaxisError) -> dict[str, Any]:
    return {"status": "error", **exc.as_dict()}


def _render_args(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def build_server() -> MCPServer:
    server = MCPServer(
        name="gaxis",
        version=__version__,
        instructions=INSTRUCTIONS,
        website_url="https://github.com/indexofire/gaxis",
    )

    @server.tool(name="health", description="Read-only probe: backends, presets, stage readiness.")
    def health() -> dict[str, Any]:
        return service.health().model_dump(mode="json")

    @server.tool(
        name="describe_data_schema",
        description="Profile a tidy CSV/TSV table and suggest a chart encoding.",
    )
    def describe_data_schema(data_path: str) -> dict[str, Any]:
        try:
            result = service.describe(DescribeDataRequest(data_path=data_path))
        except GaxisError as exc:
            return _error(exc)
        return result.model_dump(mode="json")

    @server.tool(
        name="render_chart_from_data",
        description=(
            "Render a publication-grade figure from user data; returns the figure, "
            "its standalone script, and a manifest binding both to the input hash."
        ),
    )
    def render_chart_from_data(
        data_path: str,
        chart_type: str | None = None,
        x: str | None = None,
        y: str | None = None,
        hue: str | None = None,
        yerr: str | None = None,
        title: str | None = None,
        xlabel: str | None = None,
        ylabel: str | None = None,
        preset: str = "default",
        palette: str | None = None,
        backend: Literal["python", "r"] = "python",
        width_mm: float | None = None,
        height_mm: float | None = None,
        dpi: int = 600,
        formats: list[str] | None = None,
        annotate_values: bool = False,
        out_dir: str | None = None,
        source_asset: str | None = None,
    ) -> dict[str, Any]:
        args = _render_args(
            data_path=data_path,
            chart_type=chart_type,
            x=x,
            y=y,
            hue=hue,
            yerr=yerr,
            title=title,
            xlabel=xlabel,
            ylabel=ylabel,
            preset=preset,
            palette=palette,
            backend=backend,
            width_mm=width_mm,
            height_mm=height_mm,
            dpi=dpi,
            formats=formats,
            annotate_values=annotate_values,
            out_dir=out_dir,
            source_asset=source_asset,
        )
        try:
            result = service.render(RenderRequest(**args))
        except GaxisError as exc:
            return _error(exc)
        return result.model_dump(mode="json")

    @server.tool(
        name="plan_chart_from_brief",
        description=(
            "Turn a natural-language figure request into a data-free plan: chart spec, required "
            "columns, style notes, open questions, plus matching knowledge-base cases."
        ),
    )
    def plan_chart_from_brief(
        brief: str,
        preset: str | None = None,
        backend: Literal["python", "r"] | None = None,
        k: int = 5,
    ) -> dict[str, Any]:
        try:
            result = service.plan_chart(
                PlanChartRequest(brief=brief, preset=preset, backend=backend, k=k)
            )
        except GaxisError as exc:
            return _error(exc)
        return result.model_dump(mode="json")

    @server.tool(
        name="ingest_paper",
        description=(
            "Ingest one paper on demand: figures, captions, citing paragraphs and code, then "
            "reproduce them into the knowledge base."
        ),
    )
    def ingest_paper(
        source: str,
        mode: Literal["kb_first", "full"] | None = None,
        min_quality: float = 0.0,
        reproduce: bool | None = None,
        timeout_s: float = 900.0,
        with_code: bool | None = None,
    ) -> dict[str, Any]:
        try:
            result = service.ingest_paper(
                IngestPaperRequest(
                    source=source,
                    mode=mode,
                    min_quality=min_quality,
                    reproduce=reproduce,
                    timeout_s=timeout_s,
                    with_code=with_code,
                )
            )
        except GaxisError as exc:
            return _error(exc)
        return result.model_dump(mode="json")

    @server.tool(
        name="search_chart_assets",
        description="Search the paper figure knowledge base (visual + caption + code semantics).",
    )
    def search_chart_assets(
        query: str = "",
        k: int = 5,
        chart_type: str | None = None,
        min_reproduction_level: str | None = None,
        preset: str | None = None,
        query_image_path: str | None = None,
        schema_path: str | None = None,
        design_tier: str | None = None,
        has_code: bool | None = None,
        dedupe: bool = True,
        render_sheet: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": query,
            "k": k,
            "dedupe": dedupe,
            "render_sheet": render_sheet,
        }
        optional = {
            "chart_type": chart_type,
            "min_reproduction_level": min_reproduction_level,
            "preset": preset,
            "query_image_path": query_image_path,
            "schema_path": schema_path,
            "design_tier": design_tier,
            "has_code": has_code,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        try:
            result = service.search_chart_assets(SearchChartAssetsRequest(**payload))
        except GaxisError as exc:
            return _error(exc)
        return result.model_dump(mode="json")

    @server.tool(
        name="get_chart_manifest",
        description="Fetch a ChartReproManifest by id (paper figure, code candidates, level).",
    )
    def get_chart_manifest(manifest_id: str) -> dict[str, Any]:
        try:
            result = service.get_chart_manifest(GetChartManifestRequest(manifest_id=manifest_id))
        except GaxisError as exc:
            return _error(exc)
        return result.model_dump(mode="json")

    @server.tool(
        name="reproduce_chart_code",
        description="Run a paper figure's code in the sandbox and grade reproduction L1/L2/L3.",
    )
    def reproduce_chart_code(
        manifest_id: str,
        code_path: str | None = None,
        data_path: str | None = None,
        timeout_s: float = 300.0,
        allow_network: bool = False,
        engine: Literal["podman", "local"] | None = None,
    ) -> dict[str, Any]:
        try:
            result = service.reproduce_chart_code(
                ReproduceChartCodeRequest(
                    manifest_id=manifest_id,
                    code_path=code_path,
                    data_path=data_path,
                    timeout_s=timeout_s,
                    allow_network=allow_network,
                    engine=engine,
                )
            )
        except GaxisError as exc:
            return _error(exc)
        return result.model_dump(mode="json")

    @server.tool(
        name="adapt_chart_code",
        description=(
            "Retrieve a verified template from the knowledge base, rebind it to local data "
            "(data path, output dir, delimiter, encoding intent), trial-run it and return the "
            "figure plus the edited script. Falls back to builtin templates only when no "
            "verified asset matches, and reports why in fallback_reason."
        ),
    )
    def adapt_chart_code(
        data_path: str,
        query: str | None = None,
        asset_id: str | None = None,
        preset: str = "default",
        backend: Literal["python", "r"] = "python",
        formats: list[str] | None = None,
        dpi: int = 600,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "data_path": data_path,
            "preset": preset,
            "backend": backend,
            "dpi": dpi,
            "dry_run": dry_run,
        }
        if query is not None:
            payload["query"] = query
        if asset_id is not None:
            payload["asset_id"] = asset_id
        if formats is not None:
            payload["formats"] = formats
        try:
            result = service.adapt_chart_code(AdaptChartCodeRequest(**payload))
        except GaxisError as exc:
            return _error(exc)
        return result.model_dump(mode="json")

    @server.tool(
        name="compose_panels",
        description=(
            "Arrange already-rendered figures (by figure id) on one publication page, keeping "
            "vector content, adding A/B/C labels and writing a CompositionManifest that records "
            "each panel's code hash."
        ),
    )
    def compose_panels(
        panel_ids: list[str],
        preset: str = "default",
        layout: str | None = None,
        width_mm: float | None = None,
        height_mm: float | None = None,
        labels: bool = True,
        uniform: bool = False,
        out_dir: str | None = None,
    ) -> dict[str, Any]:
        grid: tuple[int, int] | None = None
        if layout:
            try:
                rows, cols = layout.lower().split("x", 1)
                grid = (int(rows), int(cols))
            except ValueError:
                return _error(GaxisError("bad_layout", f"expected ROWSxCOLS, got {layout!r}"))
        try:
            manifest = service.compose(
                panel_ids,
                preset=preset,
                out_dir=Path(out_dir) if out_dir else None,
                layout=grid,
                width_mm=width_mm,
                height_mm=height_mm,
                labels=labels,
                uniform=uniform,
            )
        except GaxisError as exc:
            return _error(exc)
        return manifest.model_dump(mode="json")

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="gaxis-mcp", description="gaxis MCP server (contract v2.1)"
    )
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--uds", default="", help="unix socket path (HTTP transport only)")
    parser.add_argument("--token-env", default="GAXIS_MCP_TOKEN")
    args = parser.parse_args(argv)

    server = build_server()
    if args.transport == "stdio":
        server.run(transport="stdio")
        return

    from .http import run_http

    token = os.environ.get(args.token_env, "")
    debug = os.environ.get("GAXIS_DEBUG") == "1"
    if not token:
        if not debug:
            print(
                f"error: HTTP transport requires a bearer token; set ${args.token_env} "
                "(ADR-02/ADR-12), e.g. export GAXIS_MCP_TOKEN=$(openssl rand -hex 24)",
                file=sys.stderr,
            )
            raise SystemExit(2)
        print("warning: running without auth because GAXIS_DEBUG=1", file=sys.stderr)
    run_http(
        server,
        token=token or "debug",
        host=args.host,
        port=args.port,
        uds=args.uds or None,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
