"""Ingest by identifier: resolve -> download -> parse -> repository code (all stubbed).

No network in tests: the resolvers and the downloader are monkeypatched, but the
pipeline between them (parsing, link extraction, repo scanning, manifest rewrite,
KB ingest) is the real code.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("fitz")

from gaxis.acquire.metadata import PaperMetadata, ResolutionError
from gaxis.acquire.repo import RepoLink
from gaxis.errors import GaxisError
from gaxis.models.tools import IngestPaperRequest
from gaxis.service import ingest_paper

from .pdf_fixture import build_sample_pdf


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "LICENSE").write_text("MIT License\n")
    (repo / "plot_figure1.py").write_text(
        "import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\nfig.savefig('f.pdf')\n"
    )
    return repo


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    pdf_url: str | None,
    repo: Path | None,
    metadata: PaperMetadata | None = None,
) -> Path:
    source_pdf = build_sample_pdf(tmp_path / "downloaded.pdf")

    def fake_resolve(kind: str, identifier: str, *, email: str = "", timeout: float = 20.0):
        if metadata is not None:
            return metadata
        return PaperMetadata(
            kind=kind,
            identifier=identifier,
            title="Nitrogen stress reshapes the transcriptome",
            doi="10.1099/mgen.0.000001",
            pdf_url=pdf_url,
            note="open access via repository",
        )

    def fake_download(
        url: str,
        dest: Path,
        *,
        identifier: str = "",
        max_mb: float = 40.0,
        timeout: float = 60.0,
    ):
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / "paper.pdf"
        shutil.copyfile(source_pdf, target)
        return target

    def fake_clone(
        link: RepoLink,
        dest_root: Path,
        *,
        timeout_s: float = 120.0,
        max_mb: float = 200.0,
    ):
        assert repo is not None
        return repo

    monkeypatch.setattr("gaxis.service.resolve", fake_resolve)
    monkeypatch.setattr("gaxis.service.download_pdf", fake_download)
    monkeypatch.setattr("gaxis.service.clone_repository", fake_clone)
    return source_pdf


def test_doi_ingest_downloads_parses_and_attaches_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_repo: Path
) -> None:
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GAXIS_KB_ENABLED", "false")
    _patch_pipeline(monkeypatch, tmp_path, pdf_url="https://example.org/paper.pdf", repo=fake_repo)

    result = ingest_paper(IngestPaperRequest(source="10.1099/mgen.0.000001", mode="full"))
    assert result.source_kind == "doi"
    assert result.pdf_url == "https://example.org/paper.pdf"
    assert result.repository_urls == ["https://github.com/example/figrepo"]
    assert result.code_candidate_count >= 1
    assert result.manifest_ids

    manifest_path = next((tmp_path / "data" / "manifests").glob("*.json"))
    manifest = json.loads(manifest_path.read_text())
    candidates = manifest["code_candidates"]
    assert candidates
    assert candidates[0]["language"] == "python"
    assert candidates[0]["license"] == "MIT"
    assert candidates[0]["code_path"].endswith("plot_figure1.py")
    assert "repo example__figrepo" in result.message


def test_paywalled_paper_reports_no_pdf_and_asks_for_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path / "data"))
    _patch_pipeline(monkeypatch, tmp_path, pdf_url=None, repo=None)
    result = ingest_paper(IngestPaperRequest(source="10.1099/mgen.0.000001", mode="full"))
    assert result.pdf_url is None
    assert result.manifest_ids == []
    assert result.not_implemented is False
    assert "no open-access PDF" in result.message
    assert "pass it as a path" in result.message


def test_resolution_failure_is_a_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path / "data"))

    def boom(*args, **kwargs):
        raise ResolutionError("HTTP 404 from Crossref")

    monkeypatch.setattr("gaxis.service.resolve", boom)
    with pytest.raises(GaxisError) as excinfo:
        ingest_paper(IngestPaperRequest(source="10.1099/mgen.0.000404"))
    assert excinfo.value.code == "resolution_failed"
    assert "404" in excinfo.value.message


def test_kb_first_does_not_clone_or_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_repo: Path
) -> None:
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GAXIS_KB_ENABLED", "false")
    _patch_pipeline(monkeypatch, tmp_path, pdf_url="https://example.org/paper.pdf", repo=fake_repo)
    result = ingest_paper(IngestPaperRequest(source="10.1099/mgen.0.000001", mode="kb_first"))
    assert result.mode == "kb_first"
    assert result.manifest_ids == []
    assert result.code_candidate_count == 0
    assert result.repository_urls  # links are still reported
    manifests = list((tmp_path / "data" / "manifests").glob("*.json"))
    assert manifests == []


def test_with_code_false_skips_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_repo: Path
) -> None:
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GAXIS_KB_ENABLED", "false")
    _patch_pipeline(monkeypatch, tmp_path, pdf_url="https://example.org/paper.pdf", repo=fake_repo)
    result = ingest_paper(
        IngestPaperRequest(source="10.1099/mgen.0.000001", mode="full", with_code=False)
    )
    assert result.code_candidate_count == 0
    assert result.manifest_ids
