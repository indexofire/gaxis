"""Identifier resolution parsers — no network, canned payloads only."""

from __future__ import annotations

import pytest

from gaxis.acquire.metadata import (
    ResolutionError,
    parse_arxiv,
    parse_crossref,
    parse_pmc_oa,
    parse_pubmed,
    parse_unpaywall,
)

CROSSREF = {
    "message": {
        "DOI": "10.1099/mgen.0.000001",
        "title": ["Nitrogen stress reshapes the transcriptome"],
        "container-title": ["Microbial Genomics"],
        "issued": {"date-parts": [[2021, 3, 1]]},
        "author": [{"given": "Ada", "family": "Lovelace"}, {"family": "Turing"}],
        "abstract": "<jats:p>We measured expression.</jats:p>",
        "URL": "https://doi.org/10.1099/mgen.0.000001",
    }
}

ARXIV = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2103.00020v2</id>
    <published>2021-03-01T00:00:00Z</published>
    <title>Rarefaction curves   done right</title>
    <summary> A   method for sequencing depth normalisation. </summary>
    <author><name>Grace Hopper</name></author>
    <author><name>Alan Turing</name></author>
    <arxiv:journal_ref>ISME J</arxiv:journal_ref>
    <arxiv:doi>10.1038/example</arxiv:doi>
  </entry>
</feed>
"""

PUBMED = {
    "result": {
        "uids": ["12345678"],
        "12345678": {
            "title": "A novel enterotoxin and its regulation.",
            "fulljournalname": "International Journal of Food Microbiology",
            "pubdate": "2020 Mar 2",
            "authors": [{"name": "Suzuki Y"}, {"name": "Ono HK"}],
            "articleids": [{"idtype": "doi", "value": "10.1016/j.ijfoodmicro.2020.1"}],
        },
    }
}

PMC_OA = b"""<OA><records><record id="PMC7654321"><link format="tgz" href="ftp://ftp.ncbi.nlm.nih.gov/x.tar.gz"/>
<link format="pdf" href="ftp://ftp.ncbi.nlm.nih.gov/x.pdf"/></record></records></OA>"""


def test_crossref_metadata() -> None:
    meta = parse_crossref(CROSSREF, "10.1099/mgen.0.000001")
    assert meta.title == "Nitrogen stress reshapes the transcriptome"
    assert meta.year == 2021
    assert meta.journal == "Microbial Genomics"
    assert meta.authors == ["Ada Lovelace", "Turing"]
    assert meta.abstract == "We measured expression."
    assert meta.doi == "10.1099/mgen.0.000001"


def test_unpaywall_prefers_the_best_open_location() -> None:
    pdf, is_oa, note = parse_unpaywall(
        {"best_oa_location": {"url_for_pdf": "https://x/y.pdf", "host_type": "repository"}}
    )
    assert pdf == "https://x/y.pdf"
    assert is_oa is True
    assert "repository" in note


def test_unpaywall_closed_paper_reports_reason() -> None:
    pdf, is_oa, note = parse_unpaywall({"oa_status": "closed", "oa_locations": []})
    assert pdf is None
    assert is_oa is False
    assert "closed" in note


def test_arxiv_entry_is_parsed_including_doi_and_journal() -> None:
    meta = parse_arxiv(ARXIV)
    assert meta.identifier == "2103.00020v2"
    assert meta.title == "Rarefaction curves done right"
    assert meta.doi == "10.1038/example"
    assert meta.journal == "ISME J"
    assert meta.pdf_url == "https://arxiv.org/pdf/2103.00020v2"
    assert meta.year == 2021
    assert meta.authors == ["Grace Hopper", "Alan Turing"]


def test_pubmed_record_yields_doi_and_year() -> None:
    meta = parse_pubmed(PUBMED, "12345678")
    assert meta.doi == "10.1016/j.ijfoodmicro.2020.1"
    assert meta.year == 2020
    assert meta.authors == ["Suzuki Y", "Ono HK"]
    assert meta.landing_url
    assert "12345678" in meta.landing_url


def test_pmc_oa_link_is_upgraded_to_https() -> None:
    assert parse_pmc_oa(PMC_OA) == "https://ftp.ncbi.nlm.nih.gov/x.pdf"


def test_missing_pubmed_record_raises() -> None:
    with pytest.raises(ResolutionError):
        parse_pubmed({"result": {}}, "999")
