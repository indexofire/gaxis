"""The MCP surface: contract fidelity, transport auth, and real tool calls."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from gaxis.client import GaxisClient
from gaxis.mcp.server import build_server
from gaxis.models.tools import TOOL_SPECS, RenderRequest, SearchChartAssetsRequest

from .conftest import TOKEN, free_port

DATA = Path(__file__).parent / "data" / "expr.csv"


def test_registered_tools_match_the_frozen_contract() -> None:
    tools = asyncio.run(build_server().list_tools())
    assert {tool.name for tool in tools} == {spec.name for spec in TOOL_SPECS}
    by_name = {tool.name: tool for tool in tools}
    for spec in TOOL_SPECS:
        properties = set(by_name[spec.name].input_schema.get("properties", {}))
        assert properties == set(spec.input_schema["properties"]), spec.name


def test_every_tool_declares_a_description() -> None:
    tools = asyncio.run(build_server().list_tools())
    for tool in tools:
        assert tool.description, tool.name
        assert len(tool.description) > 20, tool.name


def test_http_requires_a_bearer_token(live_server: str) -> None:
    request = urllib.request.Request(
        live_server,
        data=b'{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}',
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request, timeout=5)
    assert excinfo.value.code == 401


def test_health_over_streamable_http(live_server: str) -> None:
    async def run() -> None:
        async with GaxisClient(live_server, token=TOKEN, timeout_s=60) as client:
            status = await client.health()
            assert status.ok is True
            assert status.python_backend is True
            assert status.stages["render_chart_from_data"] == "ready"
            assert "search_chart_assets" in status.stages

    asyncio.run(run())


def test_describe_and_render_over_mcp(live_server: str, tmp_path: Path) -> None:
    async def run() -> None:
        async with GaxisClient(live_server, token=TOKEN, timeout_s=180) as client:
            described = await client.describe_data_schema(str(DATA))
            assert described.data_schema.n_rows == 48
            assert described.suggested_spec.x == "genotype"

            rendered = await client.render_chart_from_data(
                RenderRequest(
                    data_path=str(DATA),
                    out_dir=str(tmp_path),
                    preset="nature_microbiology",
                    formats=["pdf"],
                )
            )
            assert rendered.figure_id.startswith("bar-")
            assert Path(rendered.code_path).is_file()
            assert rendered.lint.ok, rendered.lint.format_text()
            manifest = json.loads(Path(rendered.manifest_path).read_text())
            assert manifest["data"]["sha256"]

    asyncio.run(run())


def test_ingest_paper_over_mcp(live_server: str, tmp_path: Path) -> None:
    from gaxis.models.tools import IngestPaperRequest

    from .pdf_fixture import build_sample_pdf

    pdf = build_sample_pdf(tmp_path / "paper.pdf")

    async def run() -> None:
        async with GaxisClient(live_server, token=TOKEN, timeout_s=120) as client:
            result = await client.ingest_paper(IngestPaperRequest(source=str(pdf), mode="kb_first"))
            assert result.source_kind == "pdf"
            assert result.mode == "kb_first"
            assert result.charts_found == 1
            assert result.not_implemented is False

            from gaxis.errors import GaxisError

            with pytest.raises(GaxisError) as excinfo:
                await client.ingest_paper(IngestPaperRequest(source="not a paper"))
            assert excinfo.value.code == "unrecognised_source"

    asyncio.run(run())


def test_errors_come_back_as_stable_codes(live_server: str, tmp_path: Path) -> None:
    from gaxis.errors import GaxisError

    async def run() -> None:
        async with GaxisClient(live_server, token=TOKEN, timeout_s=60) as client:
            with pytest.raises(GaxisError) as excinfo:
                await client.render_chart_from_data(
                    RenderRequest(data_path=str(DATA), out_dir=str(tmp_path), x="nope")
                )
            assert excinfo.value.code == "unknown_column"
            with pytest.raises(GaxisError) as missing:
                await client.describe_data_schema("/nonexistent/file.csv")
            assert missing.value.code == "data_not_found"

    asyncio.run(run())


def test_plan_from_brief_over_mcp(live_server: str) -> None:
    from gaxis.models.tools import PlanChartRequest

    async def run() -> None:
        async with GaxisClient(live_server, token=TOKEN, timeout_s=60) as client:
            result = await client.plan_chart_from_brief(
                PlanChartRequest(
                    brief="grouped bar chart with error bars, Nature Microbiology, ggplot2",
                )
            )
            assert result.plan.spec.chart_type.value == "bar"
            assert result.plan.spec.preset == "nature_microbiology"
            assert result.plan.spec.backend == "r"
            assert {c.role for c in result.plan.required_columns} == {"x", "y", "hue"}
            assert result.degraded is False  # KB is reachable (fake), it just has no case yet
            assert result.matches == []

    asyncio.run(run())


def test_paper_side_tools_report_empty_state_honestly(live_server: str) -> None:
    async def run() -> None:
        async with GaxisClient(live_server, token=TOKEN, timeout_s=60) as client:
            search = await client.search_chart_assets(
                SearchChartAssetsRequest(query="16S rarefaction")
            )
            assert search.degraded is False  # reachable, simply empty
            assert search.assets == []
            assert search.message

            manifest = await client.get_chart_manifest("paper/figure-1")
            assert manifest.found is False
            assert "ingest_paper" in manifest.message

    asyncio.run(run())


def test_adapt_degrades_to_builtin_templates(live_server: str, tmp_path: Path) -> None:
    from gaxis.models.tools import AdaptChartCodeRequest

    async def run() -> None:
        async with GaxisClient(live_server, token=TOKEN, timeout_s=180) as client:
            adapted = await client.adapt_chart_code(
                AdaptChartCodeRequest(
                    data_path=str(DATA),
                    query="grouped bar with error bars",
                    preset="asm",
                    formats=["pdf"],
                )
            )
            assert adapted.source == "builtin_templates"
            assert adapted.not_implemented is False
            assert "no verified template" in adapted.fallback_reason or (
                "knowledge base disabled" in adapted.fallback_reason
            )
            assert Path(adapted.code_path).is_file()

    asyncio.run(run())


def test_compose_panels_over_mcp(live_server: str, tmp_path: Path) -> None:
    from gaxis.models.tools import ComposePanelsRequest, RenderRequest

    async def run() -> None:
        async with GaxisClient(live_server, token=TOKEN, timeout_s=180) as client:
            panels = []
            for chart, x, y in (
                ("bar", "genotype", "expr_fpkm"),
                ("line", "time_h", "od600"),
            ):
                rendered = await client.render_chart_from_data(
                    RenderRequest(
                        data_path=str(DATA),
                        out_dir=str(tmp_path / "panels"),
                        chart_type=chart,
                        x=x,
                        y=y,
                        preset="nature_microbiology",
                        formats=["pdf"],
                    )
                )
                panels.append(rendered.manifest_path)
            composition = await client.compose_panels(
                ComposePanelsRequest(
                    panel_ids=panels,
                    preset="nature_microbiology",
                    layout="1x2",
                    out_dir=str(tmp_path / "composition"),
                )
            )
            assert Path(composition.output_pdf).is_file()
            assert [panel.label for panel in composition.panels] == ["A", "B"]
            assert composition.lint.ok, composition.lint.format_text()

    asyncio.run(run())


def test_http_refuses_to_start_without_a_token(tmp_path: Path) -> None:
    port = free_port()
    env = dict(os.environ) | {"GAXIS_DATA_DIR": str(tmp_path)}
    env.pop("GAXIS_MCP_TOKEN", None)
    env.pop("GAXIS_DEBUG", None)
    completed = subprocess.run(
        [sys.executable, "-m", "gaxis.mcp.server", "--transport", "http", "--port", str(port)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 2
    assert "bearer token" in completed.stderr
