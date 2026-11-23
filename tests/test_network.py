"""Network chart (circular layout) in both backends, plus the AMR co-occurrence recipe."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaxis.analysis.amr import run_amr_cooccurrence
from gaxis.errors import GaxisError
from gaxis.models.analysis import AmrCooccurrenceParams
from gaxis.models.tools import RenderRequest
from gaxis.service import render

DATA = Path(__file__).parent / "data" / "amr_edges.csv"


def _render(tmp_path: Path, backend: str) -> Path:
    result = render(
        RenderRequest(
            data_path=str(DATA),
            out_dir=str(tmp_path / backend),
            chart_type="network",
            x="source",
            y="target",
            weight="weight",
            preset="asm",
            backend=backend,  # type: ignore[arg-type]
            formats=["pdf", "png"],
        )
    )
    assert result.lint.ok, result.lint.format_text()
    assert result.outputs
    code = Path(result.code_path).read_text(encoding="utf-8")
    assert "import gaxis" not in code
    return Path(result.outputs[0].path)


def test_network_renders_in_both_backends(tmp_path: Path) -> None:
    py_pdf = _render(tmp_path, "python")
    r_pdf = _render(tmp_path, "r")
    assert py_pdf.is_file()
    assert r_pdf.is_file()


def _amr_table(tmp_path: Path) -> Path:
    path = tmp_path / "amr.csv"
    rows = [
        ("S1", "blaCTX-M", "beta-lactam"),
        ("S1", "blaTEM", "beta-lactam"),
        ("S1", "sul1", "sulfonamide"),
        ("S2", "blaCTX-M", "beta-lactam"),
        ("S2", "blaTEM", "beta-lactam"),
        ("S2", "sul1", "sulfonamide"),
        ("S3", "blaCTX-M", "beta-lactam"),
        ("S3", "sul1", "sulfonamide"),
        ("S3", "tetA", "tetracycline"),
        ("S4", "blaCTX-M", "beta-lactam"),
        ("S4", "blaTEM", "beta-lactam"),
        ("S4", "tetA", "tetracycline"),
        ("S5", "sul1", "sulfonamide"),
        ("S5", "tetA", "tetracycline"),
        ("S6", "blaTEM", "beta-lactam"),
        ("S6", "sul1", "sulfonamide"),
    ]
    lines = ["sample,gene,gene_class", *[",".join(row) for row in rows]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_amr_cooccurrence_outputs_nodes_and_edges(tmp_path: Path) -> None:
    table = _amr_table(tmp_path)
    run = run_amr_cooccurrence(table, out_dir=tmp_path / "analysis")
    assert run.samples == 6
    assert run.genes == 4
    assert run.edges > 0
    assert Path(run.outputs["nodes"]).is_file()
    assert Path(run.outputs["edges"]).is_file()
    edges = Path(run.outputs["edges"]).read_text(encoding="utf-8")
    assert "blaCTX-M,blaTEM" in edges or "blaTEM,blaCTX-M" in edges


def test_amr_cooccurrence_rejects_bad_contract(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(GaxisError) as excinfo:
        run_amr_cooccurrence(bad, out_dir=tmp_path / "out")
    assert excinfo.value.code == "data_contract_violation"


def test_amr_cooccurrence_filters_rare_genes(tmp_path: Path) -> None:
    table = _amr_table(tmp_path)
    params = AmrCooccurrenceParams(min_prevalence=0.9, min_support=2)
    with pytest.raises(GaxisError) as excinfo:
        run_amr_cooccurrence(table, out_dir=tmp_path / "out", params=params)
    assert excinfo.value.code in {"no_genes_pass_filter", "no_edges_pass_filter"}


def test_amr_recipe_writes_a_shared_palette(tmp_path: Path) -> None:
    import json

    table = _amr_table(tmp_path)
    run = run_amr_cooccurrence(table, out_dir=tmp_path / "analysis")
    palette = Path(run.outputs["palette"])
    assert palette.is_file()
    mapping = json.loads(palette.read_text(encoding="utf-8"))
    assert set(mapping) == {"beta-lactam", "sulfonamide", "tetracycline"}
    assert all(value.startswith("#") for value in mapping.values())


def test_color_map_is_applied(tmp_path: Path) -> None:
    mapped = tmp_path / "mapped.csv"
    mapped.write_text(
        "source,target,weight,source_class,target_class\n"
        "blaCTX-M,blaTEM,0.6,beta-lactam,beta-lactam\n"
        "sul1,tetA,0.3,sulfonamide,tetracycline\n",
        encoding="utf-8",
    )
    result = render(
        RenderRequest(
            data_path=str(mapped),
            out_dir=str(tmp_path / "mapped"),
            chart_type="network",
            x="source",
            y="target",
            weight="weight",
            formats=["svg"],
            preset="asm",
            color_map={"beta-lactam": "#123456"},
        )
    )
    svg = Path(result.outputs[0].path).read_text(encoding="utf-8")
    assert "#123456" in svg.lower()
