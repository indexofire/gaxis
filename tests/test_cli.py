from pathlib import Path

from typer.testing import CliRunner

from gaxis.adapters.cli import app

runner = CliRunner()
DATA = Path(__file__).parent / "data" / "expr.csv"


def test_presets_and_tools_smoke() -> None:
    result = runner.invoke(app, ["presets"])
    assert result.exit_code == 0
    assert "nature_microbiology" in result.stdout
    tools = runner.invoke(app, ["tools", "--json"])
    assert tools.exit_code == 0
    assert '"render_chart_from_data"' in tools.stdout


def test_describe_and_health_smoke() -> None:
    described = runner.invoke(app, ["describe", "--data", str(DATA)])
    assert described.exit_code == 0
    assert "genotype" in described.stdout
    health = runner.invoke(app, ["health", "--json"])
    assert health.exit_code == 0
    assert '"ok": true' in health.stdout


def test_render_then_lint_smoke(tmp_path: Path) -> None:
    rendered = runner.invoke(
        app,
        ["render", "--data", str(DATA), "--preset", "nature_microbiology", "--out", str(tmp_path)],
    )
    assert rendered.exit_code == 0, rendered.stdout + rendered.stderr
    pdfs = list(tmp_path.rglob("*.pdf"))
    assert pdfs
    linted = runner.invoke(app, ["lint", str(pdfs[0]), "--preset", "nature_microbiology"])
    assert linted.exit_code == 0, linted.stdout


def test_manifest_command_reads_a_figure_manifest_path(tmp_path: Path) -> None:
    rendered = runner.invoke(
        app,
        ["render", "--data", str(DATA), "--preset", "asm", "--out", str(tmp_path)],
    )
    assert rendered.exit_code == 0
    manifest = next(tmp_path.rglob("manifest.json"))
    result = runner.invoke(app, ["manifest", str(manifest)])
    assert result.exit_code == 0, result.stdout
    assert "preset:" in result.stdout
    assert "lint:" in result.stdout
