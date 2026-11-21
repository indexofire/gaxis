"""Source classification for service flow 2 — offline, deterministic."""

from pathlib import Path

import pytest

from gaxis.acquire.identifiers import SourceKind, classify_source, needs_network, normalise


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("10.1099/mgen.0.000001", SourceKind.doi),
        ("https://doi.org/10.1038/s41564-020-00783-x", SourceKind.doi),
        ("arXiv:2103.00020", SourceKind.arxiv),
        ("2103.00020v2", SourceKind.arxiv),
        ("astro-ph/0601001", SourceKind.arxiv),
        ("pmid:12345678", SourceKind.pmid),
        ("12345678", SourceKind.pmid),
        ("PMC7654321", SourceKind.pmcid),
        ("https://www.nature.com/articles/s41564-020-00783-x", SourceKind.url),
    ],
)
def test_classification(source: str, kind: SourceKind) -> None:
    assert classify_source(source) is kind


def test_pdf_path_is_local_and_needs_no_network(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert classify_source(str(pdf)) is SourceKind.pdf
    assert needs_network(SourceKind.pdf) is False


def test_unknown_source_is_reported() -> None:
    assert classify_source("some random title") is SourceKind.unknown
    assert classify_source("  ") is SourceKind.unknown


def test_network_kinds() -> None:
    network_kinds = (SourceKind.doi, SourceKind.arxiv, SourceKind.pmid, SourceKind.pmcid)
    for kind in (*network_kinds, SourceKind.url):
        assert needs_network(kind) is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://doi.org/10.1099/mgen.0.000001", "10.1099/mgen.0.000001"),
        ("PMID:12345678", "12345678"),
        ("arXiv:2103.00020", "2103.00020"),
        ("10.1099/mgen.0.000001", "10.1099/mgen.0.000001"),
    ],
)
def test_normalisation_deduplicates_ids(raw: str, expected: str) -> None:
    assert normalise(raw) == expected
