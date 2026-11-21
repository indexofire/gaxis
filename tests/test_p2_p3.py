"""P2/P3: batch reproduction, preflight, dependency profiles, synthetic data."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaxis.acquire.paper import manifest_filename
from gaxis.acquire.repo import dependency_profile
from gaxis.models.paper import CodeCandidate
from gaxis.models.tools import ReproduceChartCodeResult
from gaxis.ops.runner import run_queue
from gaxis.ops.state import JobQueue
from gaxis.repro.batch import BatchItem, BatchSummary, reproduce_paper
from gaxis.repro.synthetic import generate_csv, infer_columns

from .manifest_factory import make_manifest


def _manifest_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "manifests"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _write(manifest, folder: Path) -> None:
    (folder / manifest_filename(manifest.manifest_id)).write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )


def _script(tmp_path: Path) -> Path:
    path = tmp_path / "plot_figure.py"
    path.write_text(
        "from pathlib import Path\n"
        "DATA_PATH = Path('data.csv')\n"
        "rows = DATA_PATH.read_text().splitlines()\n"
        "print(len(rows))\n",
        encoding="utf-8",
    )
    return path


def test_batch_reproduces_suitable_figures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _manifest_dir(tmp_path)
    manifest = make_manifest("pdf-abc/fig-1", level="none")
    manifest.code_candidates = [
        CodeCandidate(code_path=str(_script(tmp_path)), pairing_confidence=0.9)
    ]
    _write(manifest, folder)
    calls: list[str] = []

    def fake_reproduce(request):
        calls.append(request.manifest_id)
        return ReproduceChartCodeResult(
            manifest_id=request.manifest_id, level="L2", run_status="success", visual_similarity=0.7
        )

    monkeypatch.setattr("gaxis.service.reproduce_chart_code", fake_reproduce)
    summary = reproduce_paper("pdf-abc12345", manifests_dir=folder, min_confidence=0.6)
    assert calls == ["pdf-abc/fig-1"]
    assert summary.items[0].status == "reproduced"
    assert summary.items[0].level == "L2"


def test_batch_reports_needs_data_instead_of_guessing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _manifest_dir(tmp_path)
    manifest = make_manifest("pdf-abc/fig-2", level="none")
    manifest.code_candidates = [
        CodeCandidate(code_path=str(_script(tmp_path)), pairing_confidence=0.9)
    ]
    _write(manifest, folder)

    def failing(request):
        return ReproduceChartCodeResult(
            manifest_id=request.manifest_id,
            level="none",
            run_status="failed",
            failure_reason="FileNotFoundError: No such file or directory: 'data.csv'",
        )

    monkeypatch.setattr("gaxis.service.reproduce_chart_code", failing)
    summary = reproduce_paper("pdf-abc12345", manifests_dir=folder)
    assert summary.items[0].status == "needs_data"
    assert "--data" in summary.items[0].reason


def test_batch_low_confidence_is_skipped(tmp_path: Path) -> None:
    folder = _manifest_dir(tmp_path)
    manifest = make_manifest("pdf-abc/fig-3", level="none")
    manifest.code_candidates = [
        CodeCandidate(code_path=str(_script(tmp_path)), pairing_confidence=0.2)
    ]
    _write(manifest, folder)
    summary = reproduce_paper("pdf-abc12345", manifests_dir=folder, min_confidence=0.6)
    assert summary.items[0].status == "skipped"
    assert "confidence" in summary.items[0].reason


def test_batch_synthetic_data_is_labelled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _manifest_dir(tmp_path)
    manifest = make_manifest("pdf-abc/fig-4", level="none")
    manifest.code_candidates = [
        CodeCandidate(code_path=str(_script(tmp_path)), pairing_confidence=0.9)
    ]
    _write(manifest, folder)
    seen = {}

    def fake_reproduce(request):
        seen["data_path"] = request.data_path
        return ReproduceChartCodeResult(
            manifest_id=request.manifest_id, level="L3", run_status="success"
        )

    monkeypatch.setattr("gaxis.service.reproduce_chart_code", fake_reproduce)
    summary = reproduce_paper(
        "pdf-abc12345", manifests_dir=folder, synthetic=True, synthetic_dir=tmp_path / "synthetic"
    )
    assert summary.items[0].data_source == "synthetic"
    assert seen["data_path"] is not None
    assert Path(seen["data_path"]).is_file()


def test_ops_reproduce_job_dispatches_to_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = JobQueue(tmp_path / "ops" / "queue.db")
    queue.enqueue(["pdf-abc12345"], kind="reproduce")
    monkeypatch.setattr(
        "gaxis.repro.batch.reproduce_paper",
        lambda paper_id, **kwargs: BatchSummary(
            paper_id=paper_id,
            items=[BatchItem("pdf-abc/fig-1", "reproduced", level="L2")],
        ),
    )
    summary = run_queue(queue, limit=2)
    assert summary.processed == ["pdf-abc12345"]
    assert queue.status() == {"done": 1}
    assert "pdf-abc/fig-1" in queue.jobs()[0].manifest_ids
    queue.close()


def test_dependency_profile_reads_requirements_and_description(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text(
        "# figure stack\nmatplotlib==3.8\nnumpy>=1.26\n-git+https://example.com/x\nseaborn\n",
        encoding="utf-8",
    )
    packages = dependency_profile(repo)
    assert packages == ["matplotlib==3.8", "numpy>=1.26", "seaborn"]

    r_repo = tmp_path / "rrepo"
    r_repo.mkdir()
    (r_repo / "DESCRIPTION").write_text(
        "Package: x\nImports: ggplot2 (>= 3.4), dplyr\nDepends: R (>= 4.0)\nSuggests: testthat\n",
        encoding="utf-8",
    )
    assert dependency_profile(r_repo, language="r") == ["ggplot2", "dplyr", "testthat"]


def test_synthetic_data_is_deterministic(tmp_path: Path) -> None:
    columns = ["group", "value"]
    first = generate_csv(columns, tmp_path / "a.csv", seed="caption")
    second = generate_csv(columns, tmp_path / "b.csv", seed="caption")
    assert first.read_text() == second.read_text()
    header = first.read_text().splitlines()[0]
    assert header == "group,value"
    assert len(first.read_text().splitlines()) == 13


def test_infer_columns_reads_indexed_names(tmp_path: Path) -> None:
    script = tmp_path / "plot.py"
    script.write_text(
        'rows = read()\nfor row in rows:\n    print(row["genotype"], float(row["expr_fpkm"]))\n',
        encoding="utf-8",
    )
    assert infer_columns(script) == ["genotype", "expr_fpkm"]


def test_per_paper_packages_merge_base_and_declared(tmp_path: Path) -> None:
    from gaxis.repro.runner import _packages_digest, _paper_packages

    script = _script(tmp_path)
    manifest = make_manifest("pdf-abc/fig-5", level="none")
    manifest.code_candidates = [
        CodeCandidate(
            code_path=str(script),
            packages=["matplotlib==3.8", "seaborn"],
            pairing_confidence=0.9,
        )
    ]

    class Config:
        autobuild_packages = ("matplotlib==3.11.2", "numpy==2.5.5")

    packages = _paper_packages(manifest, script, Config())
    assert packages[0] == "matplotlib==3.11.2"
    assert "seaborn" in packages
    assert len(packages) <= 24
    assert len(_packages_digest(packages)) == 8


def test_ops_reproduce_job_already_graded_is_done_not_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = JobQueue(tmp_path / "ops" / "queue.db")
    queue.enqueue(["pdf-abc12345"], kind="reproduce")
    monkeypatch.setattr(
        "gaxis.repro.batch.reproduce_paper",
        lambda paper_id, **kwargs: BatchSummary(
            paper_id=paper_id,
            items=[BatchItem("pdf-abc12345/fig-1", "skipped", "L2", "already graded")],
        ),
    )
    summary = run_queue(queue, limit=2)
    assert summary.skipped == ["pdf-abc12345"]
    assert queue.status() == {"done": 1}
    assert queue.jobs()[0].manifest_ids == "pdf-abc12345/fig-1"
    queue.close()
