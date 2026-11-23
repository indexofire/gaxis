"""The reference bacmap adapter: gating, naming, and JSON-string results."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))

from bacmap_upstream_gaxis import GaxisUpstream
from mcp.server.mcpserver import MCPServer

from .conftest import TOKEN

DATA = Path(__file__).parent / "data" / "expr.csv"


def test_cloud_profile_hides_local_data_tools() -> None:
    upstream = GaxisUpstream(max_data_class="D1")
    visible = {spec.name for spec in upstream.visible_specs()}
    assert visible == {
        "health",
        "search_chart_assets",
        "get_chart_manifest",
        "reproduce_chart_code",
        "plan_chart_from_brief",
        "ingest_paper",
        "list_figure_recipes",
    }
    assert "render_chart_from_data" not in visible


def test_local_trusted_profile_sees_everything() -> None:
    upstream = GaxisUpstream(max_data_class="D4")
    assert len(upstream.visible_specs()) == 12


def test_register_prefixes_and_preserves_schemas() -> None:
    server = MCPServer(name="bacmap-test")
    upstream = GaxisUpstream(max_data_class="D3")
    names = upstream.register(server)
    assert set(names) == {
        "bacmap_chart_health",
        "bacmap_chart_describe_data_schema",
        "bacmap_chart_render_chart_from_data",
        "bacmap_chart_search_chart_assets",
        "bacmap_chart_get_chart_manifest",
        "bacmap_chart_reproduce_chart_code",
        "bacmap_chart_adapt_chart_code",
        "bacmap_chart_compose_panels",
        "bacmap_chart_list_figure_recipes",
        "bacmap_chart_render_figure_recipe",
        "bacmap_chart_plan_chart_from_brief",
        "bacmap_chart_ingest_paper",
    }
    assert all(name.startswith("bacmap_chart_") for name in names)
    tools = asyncio.run(server.list_tools())
    render_tool = next(t for t in tools if t.name == "bacmap_chart_render_chart_from_data")
    # bacmap's own convention: one `params` object, schema in $defs.
    schema = render_tool.input_schema
    assert list(schema["properties"]) == ["params"]
    model = schema["$defs"]["render_chart_from_dataInput"]
    assert {"data_path", "preset", "backend", "formats"} <= set(model["properties"])


def test_calls_are_gated_before_leaving_the_process() -> None:
    upstream = GaxisUpstream(url="http://127.0.0.1:1/mcp", max_data_class="D1")
    blocked = json.loads(
        upstream.call_sync("bacmap_chart_render_chart_from_data", {"data_path": str(DATA)})
    )
    assert "above the profile ceiling" in blocked["error"]


def test_health_and_render_round_trip(live_server: str, tmp_path: Path) -> None:
    upstream = GaxisUpstream(url=live_server, token=TOKEN, max_data_class="D4")
    health = json.loads(upstream.call_sync("bacmap_chart_health", {}))
    assert health["ok"] is True

    rendered = json.loads(
        upstream.call_sync(
            "bacmap_chart_render_chart_from_data",
            {
                "data_path": str(DATA),
                "preset": "nature_microbiology",
                "formats": ["pdf"],
                "out_dir": str(tmp_path),
            },
        )
    )
    assert rendered["figure_id"].startswith("bar-")
    assert Path(rendered["code_path"]).is_file()
    assert rendered["lint"]["issues"] == []


def test_kernel_errors_become_json_errors(live_server: str, tmp_path: Path) -> None:
    upstream = GaxisUpstream(url=live_server, token=TOKEN, max_data_class="D4")
    failed = json.loads(
        upstream.call_sync(
            "bacmap_chart_render_chart_from_data",
            {"data_path": str(DATA), "y": "condition", "out_dir": str(tmp_path)},
        )
    )
    assert failed["code"] == "not_numeric"
    assert failed["error"]


def test_unreachable_server_is_reported_not_raised() -> None:
    upstream = GaxisUpstream(url="http://127.0.0.1:1/mcp", token="x", max_data_class="D1")
    payload = json.loads(upstream.call_sync("bacmap_chart_health", {}))
    assert "unreachable" in payload["error"]


def test_unknown_tool_name_is_reported() -> None:
    upstream = GaxisUpstream(max_data_class="D4")
    payload = json.loads(upstream.call_sync("bacmap_chart_nope", {}))
    assert "unknown gaxis tool" in payload["error"]


def test_invalid_data_class_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown data class"):
        GaxisUpstream(max_data_class="D9")
