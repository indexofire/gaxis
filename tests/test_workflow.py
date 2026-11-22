"""Snakemake workflow scaffolding (snp-tree) and dry-run validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gaxis.analysis.workflows import scaffold_snp_tree
from gaxis.errors import GaxisError
from gaxis.service import analysis_scaffold, analysis_workflows


def _alignment(tmp_path: Path) -> Path:
    path = tmp_path / "aln.fasta"
    path.write_text(">A\nACGTACGTACGT\n>B\nACGTACGTACGA\n>C\nACGTACGTTCGA\n", encoding="utf-8")
    return path


def test_scaffold_writes_a_valid_project(tmp_path: Path) -> None:
    alignment = _alignment(tmp_path)
    scaffold = scaffold_snp_tree(tmp_path / "wf", alignment=alignment, threads=2)
    out = Path(scaffold.out_dir)
    for name in ("Snakefile", "config.yaml", "README.md", "workflow.json"):
        assert (out / name).is_file()
    payload = json.loads((out / "workflow.json").read_text())
    assert payload["workflow_id"] == "snp-tree"
    assert payload["files_sha256"]
    assert "iqtree" in (out / "Snakefile").read_text()


def test_check_reports_missing_alignment(tmp_path: Path) -> None:
    with pytest.raises(GaxisError) as excinfo:
        analysis_scaffold(
            "snp-tree",
            out_dir=tmp_path / "wf",
            alignment=tmp_path / "missing.fasta",
            check=True,
        )
    assert excinfo.value.code == "data_not_found"


def test_snakemake_dry_run_validates_the_dag(tmp_path: Path) -> None:
    alignment = _alignment(tmp_path)
    scaffold, output = analysis_scaffold(
        "snp-tree", out_dir=tmp_path / "wf", alignment=alignment, threads=2, check=True
    )
    assert scaffold.check
    assert "dry-run" in output.lower() or "job" in output.lower()


def test_workflow_catalog_lists_snp_tree() -> None:
    entries = analysis_workflows()
    assert entries[0]["id"] == "snp-tree"
    assert "results/tree.nwk" in entries[0]["outputs"]
