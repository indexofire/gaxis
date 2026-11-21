"""M2 end-to-end: sandbox -> compare -> grade -> manifest update."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("fitz")

from gaxis.acquire.paper import load_manifest
from gaxis.errors import GaxisError
from gaxis.models.tools import (
    IngestPaperRequest,
    ReproduceChartCodeRequest,
)
from gaxis.service import ingest_paper, reproduce_chart_code

from .pdf_fixture import build_sample_pdf


@pytest.fixture
def paper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, str]:
    root = tmp_path / "data"
    monkeypatch.setenv("GAXIS_DATA_DIR", str(root))
    monkeypatch.setenv("GAXIS_SANDBOX_BACKEND", "local")
    pdf = build_sample_pdf(tmp_path / "paper.pdf")
    result = ingest_paper(IngestPaperRequest(source=str(pdf), mode="full"))
    manifest_id = result.manifest_ids[0]
    manifest = load_manifest(manifest_id, root / "manifests")
    assert manifest is not None
    reference = root / manifest.chart_file
    return root, reference, manifest_id


def test_reproduction_runs_compares_and_grades_l1(
    paper: tuple[Path, Path, str], tmp_path: Path
) -> None:
    root, reference, manifest_id = paper
    script = tmp_path / "figure.py"
    script.write_text(
        "import os, shutil\nshutil.copyfile(os.environ['GAXIS_DATA'], 'reproduced.png')\n"
    )
    result = reproduce_chart_code(
        ReproduceChartCodeRequest(
            manifest_id=manifest_id,
            code_path=str(script),
            data_path=str(reference),
            engine="local",
        )
    )
    assert result.run_status == "success"
    assert result.engine == "local"
    assert result.level == "L1", result.failure_reason
    assert result.visual_similarity is not None
    assert result.visual_similarity > 0.95
    assert result.outputs
    assert Path(result.outputs[0].path).is_file()
    assert result.sandbox_report["network_enforced"] is False
    assert result.sandbox_report["scan"]["blocking"] is False
    assert result.code_sha256

    stored = load_manifest(manifest_id, root / "manifests")
    assert stored is not None
    assert stored.reproduction.level == "L1"
    assert stored.reproduction.sandbox_run_status == "success"
    assert stored.reproduction.render_output
    assert stored.code_candidates
    assert stored.code_candidates[0].language == "python"


def test_blocked_script_never_executes(paper: tuple[Path, Path, str], tmp_path: Path) -> None:
    _, _, manifest_id = paper
    script = tmp_path / "evil.py"
    script.write_text("import os\nos.system('touch /tmp/gaxis-should-not-exist')\n")
    result = reproduce_chart_code(
        ReproduceChartCodeRequest(manifest_id=manifest_id, code_path=str(script), engine="local")
    )
    assert result.level == "none"
    assert result.run_status == "skipped"
    assert "static scan blocked" in result.failure_reason
    assert result.sandbox_report["scan"]["blocking"] is True


def test_copyleft_code_is_refused(paper: tuple[Path, Path, str], tmp_path: Path) -> None:
    _, _, manifest_id = paper
    script = tmp_path / "gpl.py"
    script.write_text('"""GNU General Public License v3."""\nprint("hi")\n')
    result = reproduce_chart_code(
        ReproduceChartCodeRequest(manifest_id=manifest_id, code_path=str(script), engine="local")
    )
    assert result.level == "none"
    assert "copyleft" in result.failure_reason


def test_failing_script_grades_l3_with_reason(
    paper: tuple[Path, Path, str], tmp_path: Path
) -> None:
    _, _, manifest_id = paper
    script = tmp_path / "broken.py"
    script.write_text("raise RuntimeError('boom')\n")
    result = reproduce_chart_code(
        ReproduceChartCodeRequest(manifest_id=manifest_id, code_path=str(script), engine="local")
    )
    assert result.level == "L3"
    assert result.run_status == "failed"
    assert "does not run" in result.failure_reason
    assert "boom" in result.failure_reason


def test_timeout_is_recorded(paper: tuple[Path, Path, str], tmp_path: Path) -> None:
    _, _, manifest_id = paper
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n")
    result = reproduce_chart_code(
        ReproduceChartCodeRequest(
            manifest_id=manifest_id, code_path=str(script), engine="local", timeout_s=1
        )
    )
    assert result.level == "L3"
    assert "timed out" in result.failure_reason


def test_unsupported_language_is_refused(paper: tuple[Path, Path, str], tmp_path: Path) -> None:
    _, _, manifest_id = paper
    script = tmp_path / "figure.jl"
    script.write_text("using Plots\n")
    with pytest.raises(GaxisError) as excinfo:
        reproduce_chart_code(
            ReproduceChartCodeRequest(manifest_id=manifest_id, code_path=str(script))
        )
    assert excinfo.value.code == "unsupported_language"


def test_missing_code_path_is_a_typed_error(paper: tuple[Path, Path, str]) -> None:
    _, _, manifest_id = paper
    with pytest.raises(GaxisError) as excinfo:
        reproduce_chart_code(ReproduceChartCodeRequest(manifest_id=manifest_id))
    assert excinfo.value.code == "code_required"


def test_unknown_manifest_is_a_typed_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path))
    script = tmp_path / "s.py"
    script.write_text("print('x')\n")
    with pytest.raises(GaxisError) as excinfo:
        reproduce_chart_code(
            ReproduceChartCodeRequest(manifest_id="pdf-deadbeef/fig-1", code_path=str(script))
        )
    assert excinfo.value.code == "manifest_not_found"


def test_reproduction_json_is_written(paper: tuple[Path, Path, str], tmp_path: Path) -> None:
    root, reference, manifest_id = paper
    script = tmp_path / "figure.py"
    script.write_text("import os, shutil\nshutil.copyfile(os.environ['GAXIS_DATA'], 'out.png')\n")
    result = reproduce_chart_code(
        ReproduceChartCodeRequest(
            manifest_id=manifest_id, code_path=str(script), data_path=str(reference), engine="local"
        )
    )
    report = next((root / "repro").rglob("reproduction.json"))
    payload = json.loads(report.read_text())
    assert payload["manifest_id"] == manifest_id
    assert payload["code_sha256"] == result.code_sha256
    assert payload["similarity"]["score"] == pytest.approx(result.visual_similarity, abs=1e-3)


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not installed")
def test_r_reproduction_runs_in_the_r_engine(paper: tuple[Path, Path, str], tmp_path: Path) -> None:
    _, _, manifest_id = paper
    script = tmp_path / "figure.R"
    script.write_text(
        "suppressPackageStartupMessages(library(ggplot2))\n"
        "d <- data.frame(g = c('WT', 'dpsA', 'rpoS', 'hfq'), y = c(120, 85, 150, 95))\n"
        "p <- ggplot(d, aes(g, y)) + geom_col(fill = '#009E73') + theme_classic()\n"
        "ggsave('figure.png', p, width = 60, height = 40, units = 'mm', dpi = 300)\n"
    )
    result = reproduce_chart_code(
        ReproduceChartCodeRequest(manifest_id=manifest_id, code_path=str(script), engine="local")
    )
    assert result.language == "r"
    assert result.run_status == "success", result.failure_reason
    assert result.outputs
    assert result.outputs[0].format == "png"
    assert result.level in {"L1", "L2", "L3"}


def test_reproduction_assetizes_code_and_records_data_source(
    paper: tuple[Path, Path, str], tmp_path: Path
) -> None:
    root, reference, manifest_id = paper
    script = tmp_path / "figure.py"
    script.write_text(
        "import os, shutil\nshutil.copyfile(os.environ['GAXIS_DATA'], 'reproduced.png')\n"
    )
    result = reproduce_chart_code(
        ReproduceChartCodeRequest(
            manifest_id=manifest_id,
            code_path=str(script),
            data_path=str(reference),
            engine="local",
        )
    )
    stored = load_manifest(manifest_id, root / "manifests")
    assert stored is not None
    candidate = stored.code_candidates[-1]
    assert candidate.code_sha256 == result.code_sha256
    asset = Path(candidate.code_path)
    assert asset.is_file()
    assert "assets/code" in str(asset)
    assert stored.reproduction.data_source == "user"
    assert stored.reproduction.environment_lock == "local"
