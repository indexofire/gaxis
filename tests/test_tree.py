"""Newick conversion and tree rendering in both backends."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaxis.analysis.tree import parse_newick, run_newick_to_table
from gaxis.errors import GaxisError
from gaxis.models.tools import RenderRequest
from gaxis.service import render

NEWICK = "((A:0.1,B:0.2)X:0.3,(C:0.05,D:0.15)Y:0.25)root:0.0;"


def test_parse_newick_builds_edges() -> None:
    edges = parse_newick(NEWICK)
    assert len(edges) == 6
    assert {edge["child"] for edge in edges} == {"A", "B", "C", "D", "X", "Y"}
    assert all(edge["branch_length"] > 0 for edge in edges)


def test_parse_newick_strips_comments_and_quotes() -> None:
    edges = parse_newick("('a b':1.0,[&x=1]c:2.0)root;")
    assert {edge["child"] for edge in edges} == {"a b", "c"}


def test_parse_newick_rejects_garbage() -> None:
    with pytest.raises(GaxisError) as excinfo:
        parse_newick("(A,B")
    assert excinfo.value.code == "tree_parse_failed"


def _edges(tmp_path: Path) -> Path:
    run = run_newick_to_table((tmp_path / "tree.nwk"), out_dir=tmp_path / "out") if False else None
    tree = tmp_path / "tree.nwk"
    tree.write_text(NEWICK, encoding="utf-8")
    run = run_newick_to_table(tree, out_dir=tmp_path / "out")
    return Path(run.outputs["tree_edges"])


def test_tree_renders_in_both_backends(tmp_path: Path) -> None:
    edges = _edges(tmp_path)
    for backend in ("python", "r"):
        result = render(
            RenderRequest(
                data_path=str(edges),
                out_dir=str(tmp_path / backend),
                chart_type="tree",
                x="parent",
                y="child",
                weight="branch_length",
                preset="asm",
                backend=backend,  # type: ignore[arg-type]
                formats=["pdf", "png"],
            )
        )
        assert result.lint.ok, result.lint.format_text()
        assert result.outputs
        code = Path(result.code_path).read_text(encoding="utf-8")
        assert "import gaxis" not in code
