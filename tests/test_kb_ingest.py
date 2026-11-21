"""Idempotent ingestion: unchanged pages are skipped, re-validated ones are rewritten."""

from __future__ import annotations

from pathlib import Path

from gaxis.config import load_config
from gaxis.kb.gbrain import GbrainCLI
from gaxis.kb.ingest import KbIngestor

from .manifest_factory import make_manifest


def _ingestor(tmp_path: Path) -> KbIngestor:
    kb = GbrainCLI(load_config().knowledge)
    return KbIngestor(kb, state_path=tmp_path / "data" / "kb" / "state.json")


def test_first_ingest_writes_every_page(fake_kb: Path, tmp_path: Path) -> None:
    ingestor = _ingestor(tmp_path)
    summary = ingestor.ingest([make_manifest(), make_manifest("pdf-abc12345/fig-2")])
    assert summary.ok
    assert len(summary.upserted) == 2
    assert summary.skipped == []
    assert (tmp_path / "data" / "kb" / "state.json").is_file()


def test_second_ingest_skips_unchanged_pages(fake_kb: Path, tmp_path: Path) -> None:
    ingestor = _ingestor(tmp_path)
    manifests = [make_manifest(), make_manifest("pdf-abc12345/fig-2")]
    ingestor.ingest(manifests)
    summary = ingestor.ingest(manifests)
    assert summary.upserted == []
    assert len(summary.skipped) == 2


def test_revalidated_asset_is_rewritten(fake_kb: Path, tmp_path: Path) -> None:
    ingestor = _ingestor(tmp_path)
    ingestor.ingest([make_manifest(level="L2")])
    summary = ingestor.ingest([make_manifest(level="L1")])
    assert summary.upserted == ["pdf-abc12345/fig-1"]
    page = GbrainCLI(load_config().knowledge).get_page("paper-kb:pdf-abc12345-fig-1")
    assert page is not None
    assert page["frontmatter"]["reproduction_level"] == "L1"


def test_force_rewrites_even_when_unchanged(fake_kb: Path, tmp_path: Path) -> None:
    ingestor = _ingestor(tmp_path)
    manifests = [make_manifest()]
    ingestor.ingest(manifests)
    summary = ingestor.ingest(manifests, force=True)
    assert summary.upserted == ["pdf-abc12345/fig-1"]


def test_unavailable_brain_degrades_without_raising(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAXIS_GBRAIN_BIN", str(tmp_path / "missing-gbrain"))
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path / "data"))
    ingestor = KbIngestor(GbrainCLI(load_config().knowledge), state_path=tmp_path / "state.json")
    summary = ingestor.ingest([make_manifest()])
    assert summary.ok is False
    assert summary.unavailable
    assert "unavailable" in summary.message()
