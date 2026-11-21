import json
import shutil
import sys
from pathlib import Path

import pytest

from gaxis.errors import GaxisError
from gaxis.models.spec import ChartType
from gaxis.models.tools import RenderRequest
from gaxis.service import render

DATA = Path(__file__).parent / "data" / "expr.csv"


def test_render_bar_end_to_end(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    result = render(
        RenderRequest(
            data_path=str(DATA),
            out_dir=str(tmp_path),
            preset="nature_microbiology",
            formats=["pdf", "png"],
        )
    )
    assert result.figure_id.startswith("bar-")
    assert Path(result.code_path).is_file()
    assert result.lint.ok, result.lint.format_text()
    assert {o.format for o in result.outputs} == {"pdf", "png"}
    for output in result.outputs:
        assert Path(output.path).stat().st_size > 2048
        assert output.width_mm == pytest.approx(89.0, abs=3.0)

    manifest = json.loads(Path(result.manifest_path).read_text())
    assert manifest["preset"] == "nature_microbiology"
    assert manifest["data"]["sha256"]
    assert manifest["code_sha256"]
    assert manifest["outputs"]
    assert "matplotlib" in Path(result.code_path).read_text()


def test_generated_script_is_standalone_and_rerunnable(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    result = render(
        RenderRequest(data_path=str(DATA), out_dir=str(tmp_path), preset="asm", formats=["pdf"])
    )
    code = Path(result.code_path).read_text()
    assert "import gaxis" not in code
    assert "savefig" in code

    from gaxis.exec.runner import run_script

    rerun = run_script(Path(result.code_path), cwd=Path(result.code_path).parent)
    assert rerun.returncode == 0, rerun.stderr


@pytest.mark.parametrize("chart", ["bar", "stacked_bar", "line", "scatter", "box", "heatmap"])
def test_every_chart_type_renders(tmp_path: Path, chart: str) -> None:
    pytest.importorskip("matplotlib")
    spec_chart = ChartType(chart)
    overrides: dict[str, object] = {"chart_type": spec_chart}
    if spec_chart in (ChartType.line, ChartType.scatter):
        overrides |= {"x": "od600", "y": "expr_fpkm"}
    elif spec_chart is ChartType.box:
        overrides |= {"x": "genotype", "y": "expr_fpkm"}
    elif spec_chart is ChartType.heatmap:
        overrides |= {"x": "genotype", "y": "expr_fpkm", "hue": "condition"}
    result = render(
        RenderRequest(data_path=str(DATA), out_dir=str(tmp_path), preset="default", **overrides)  # type: ignore[arg-type]
    )
    assert result.lint.ok, result.lint.format_text()


def test_unknown_column_is_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(GaxisError) as excinfo:
        render(RenderRequest(data_path=str(DATA), out_dir=str(tmp_path), x="nope", y="expr_fpkm"))
    assert excinfo.value.code == "unknown_column"


def test_non_numeric_y_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(GaxisError) as excinfo:
        render(
            RenderRequest(data_path=str(DATA), out_dir=str(tmp_path), x="genotype", y="condition")
        )
    assert excinfo.value.code == "not_numeric"


needs_r = pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not installed")


@needs_r
def test_r_backend_renders_publication_figure(tmp_path: Path) -> None:
    result = render(
        RenderRequest(
            data_path=str(DATA),
            out_dir=str(tmp_path),
            preset="nature_microbiology",
            backend="r",
            formats=["pdf", "png"],
        )
    )
    assert result.lint.ok, result.lint.format_text()
    code = Path(result.code_path).read_text()
    assert "ggplot" in code
    assert {o.format for o in result.outputs} == {"pdf", "png"}
    for output in result.outputs:
        assert output.width_mm == pytest.approx(89.0, abs=6.0)


@pytest.mark.parametrize("backend", ["python", "r"])
def test_panel_source_mode_skips_writing(tmp_path: Path, backend: str) -> None:
    """Composition (M4) sources a panel script and expects the figure, not files."""
    import os
    import subprocess

    if backend == "r" and shutil.which("Rscript") is None:
        pytest.skip("Rscript not installed")
    result = render(
        RenderRequest(data_path=str(DATA), out_dir=str(tmp_path), backend=backend, formats=["pdf"])
    )
    figure_dir = Path(result.code_path).parent
    for produced in figure_dir.glob("*.pdf"):
        produced.unlink()
    argv = (
        [sys.executable, result.code_path]
        if backend == "python"
        else [
            shutil.which("Rscript") or "Rscript",
            result.code_path,
        ]
    )
    completed = subprocess.run(
        argv,
        cwd=figure_dir,
        capture_output=True,
        text=True,
        env=dict(os.environ) | {"GAXIS_PANEL_SOURCE": "1"},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert list(figure_dir.glob("*.pdf")) == []
