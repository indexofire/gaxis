"""Service flow 2 entry: classification is real today, parsing is M1/M2."""

from pathlib import Path

import pytest

from gaxis.acquire.identifiers import SourceKind, classify_source, needs_network
from gaxis.errors import GaxisError
from gaxis.models.tools import IngestPaperRequest
from gaxis.service import ingest_paper


def test_doi_is_routed_as_network_source_with_kb_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gaxis.acquire.metadata import PaperMetadata

    monkeypatch.setattr(
        "gaxis.service.resolve",
        lambda kind, identifier, **_: PaperMetadata(
            kind=kind,
            identifier=identifier,
            title="T",
            note="no open-access PDF (oa_status=closed)",
        ),
    )
    result = ingest_paper(IngestPaperRequest(source="10.1099/mgen.0.000001"))
    assert result.source_kind == "doi"
    assert result.needs_network is True
    assert result.mode == "kb_first"
    assert result.deep_parse_suggested is True
    assert result.not_implemented is False
    assert result.pdf_url is None
    assert "no open-access PDF" in result.message


def test_local_pdf_needs_no_network(tmp_path: Path) -> None:
    assert classify_source(str(tmp_path / "paper.pdf")) is SourceKind.pdf
    assert needs_network(SourceKind.pdf) is False


def test_unreadable_pdf_is_a_typed_error(tmp_path: Path) -> None:
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"%PDF-1.4 broken")
    with pytest.raises(GaxisError) as excinfo:
        ingest_paper(IngestPaperRequest(source=str(pdf)))
    assert excinfo.value.code == "pdf_unreadable"


def test_full_mode_skips_the_kb_first_suggestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gaxis.acquire.metadata import PaperMetadata

    monkeypatch.setattr(
        "gaxis.service.resolve",
        lambda kind, identifier, **_: PaperMetadata(
            kind=kind, identifier=identifier, title="T", note="no open-access PDF"
        ),
    )
    result = ingest_paper(IngestPaperRequest(source="PMID:12345678", mode="full"))
    assert result.mode == "full"
    assert result.deep_parse_suggested is False
    assert result.pdf_url is None


def test_unknown_source_is_a_typed_error() -> None:
    with pytest.raises(GaxisError) as excinfo:
        ingest_paper(IngestPaperRequest(source="that paper my colleague mentioned"))
    assert excinfo.value.code == "unrecognised_source"


def test_network_can_be_disabled_by_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "gaxis.toml"
    config.write_text("[ingest]\nallow_network = false\n")
    monkeypatch.setenv("GAXIS_CONFIG", str(config))
    with pytest.raises(GaxisError) as excinfo:
        ingest_paper(IngestPaperRequest(source="10.1099/mgen.0.000001"))
    assert excinfo.value.code == "network_disabled"
