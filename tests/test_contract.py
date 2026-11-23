import json
from pathlib import Path

from gaxis.models.tools import TOOL_SPECS

SNAPSHOT = Path(__file__).parent / "contract_snapshot.json"
CONTRACT_VERSION = "v2.8"
EXPECTED_TOOLS = {
    "describe_data_schema",
    "render_chart_from_data",
    "search_chart_assets",
    "get_chart_manifest",
    "reproduce_chart_code",
    "adapt_chart_code",
    "compose_panels",
    "list_figure_recipes",
    "render_figure_recipe",
    "plan_chart_from_brief",
    "ingest_paper",
    "health",
}
IMPLEMENTED_NOW = {
    "describe_data_schema",
    "render_chart_from_data",
    "adapt_chart_code",
    "compose_panels",
    "list_figure_recipes",
    "render_figure_recipe",
    "plan_chart_from_brief",
    "get_chart_manifest",
    "ingest_paper",
    "search_chart_assets",
    "reproduce_chart_code",
    "health",
}


def test_tool_names_are_frozen() -> None:
    assert {spec.name for spec in TOOL_SPECS} == EXPECTED_TOOLS


def test_implemented_flags_match_m0_scope() -> None:
    assert {spec.name for spec in TOOL_SPECS if spec.implemented} == IMPLEMENTED_NOW


def test_every_tool_declares_gating_metadata() -> None:
    for spec in TOOL_SPECS:
        assert spec.data_class in {"D1", "D2", "D3", "D4"}
        assert spec.cost in {"ms", "s", "min", "10min+"}
        assert spec.input_schema["type"] == "object"
        assert spec.output_schema["type"] == "object"
        assert isinstance(spec.needs_network, bool)
        assert isinstance(spec.side_effects, list)


def test_contract_snapshot_is_current() -> None:
    current = {
        spec.name: {
            "data_class": str(spec.data_class),
            "inputs": sorted(spec.input_schema.get("properties", {})),
            "outputs": sorted(spec.output_schema.get("properties", {})),
        }
        for spec in TOOL_SPECS
    }
    assert SNAPSHOT.exists(), (
        "missing contract snapshot; regenerate it with scripts/freeze_contract.py"
    )
    snapshot = json.loads(SNAPSHOT.read_text())
    assert snapshot["contract_version"] == CONTRACT_VERSION
    assert snapshot["tools"] == current, (
        "tool contract changed — intentional? bump CONTRACT_VERSION and refresh the snapshot"
    )
