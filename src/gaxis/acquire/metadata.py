"""Identifier resolution: DOI / arXiv / PubMed -> metadata + an open PDF URL.

Parsing is separated from fetching so the parsers are unit-testable offline
(`parse_crossref`, `parse_unpaywall`, `parse_arxiv`, `parse_pubmed`). The fetchers
are thin urllib wrappers with an explicit User-Agent — Crossref, Unpaywall and NCBI
all expect one, and Unpaywall requires a contact email.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

USER_AGENT = "gaxis/0.6 (+https://github.com/indexofire/gaxis; scholarly figure reproduction)"
ARXIV_API = "http://export.arxiv.org/api/query"
CROSSREF_API = "https://api.crossref.org/works"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
PUBMED_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PMC_OA = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"


class ResolutionError(RuntimeError):
    """The identifier could not be resolved (network error, paywall, bad id)."""


@dataclass
class PaperMetadata:
    kind: str
    identifier: str
    title: str = ""
    doi: str = ""
    year: int | None = None
    journal: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    pdf_url: str | None = None
    landing_url: str | None = None
    open_access: bool = False
    note: str = ""


def _get(url: str, *, timeout: float = 20.0, accept: str = "*/*") -> bytes:
    request = urllib.request.Request(  # noqa: S310 - https endpoints from constants
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise ResolutionError(f"request failed for {url}: {exc}") from exc


def _get_json(url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    payload = _get(url, timeout=timeout, accept="application/json")
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ResolutionError(f"non-JSON response from {url}") from exc


# ------------------------------------------------------------------ parsers
def parse_crossref(payload: dict[str, Any], doi: str) -> PaperMetadata:
    message = payload.get("message") or {}
    titles = message.get("title") or []
    authors = [
        " ".join(filter(None, [author.get("given"), author.get("family")]))
        for author in message.get("author") or []
    ]
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
            break
    containers = message.get("container-title") or []
    return PaperMetadata(
        kind="doi",
        identifier=doi,
        title=titles[0] if titles else "",
        doi=message.get("DOI") or doi,
        year=year,
        journal=containers[0] if containers else "",
        authors=authors,
        abstract=re.sub(r"<[^>]+>", "", message.get("abstract") or "").strip(),
        landing_url=message.get("URL"),
    )


def parse_unpaywall(payload: dict[str, Any]) -> tuple[str | None, bool, str]:
    """Return (pdf_url, is_oa, note)."""
    best = payload.get("best_oa_location") or {}
    pdf_url = best.get("url_for_pdf") or best.get("url")
    if pdf_url:
        return str(pdf_url), True, f"open access via {best.get('host_type') or 'repository'}"
    locations = payload.get("oa_locations") or []
    for location in locations:
        candidate = location.get("url_for_pdf") or location.get("url")
        if candidate:
            return str(candidate), True, "open access via alternative location"
    status = payload.get("oa_status") or "closed"
    return None, False, f"no open-access PDF (oa_status={status})"


def parse_arxiv(payload: bytes) -> PaperMetadata:
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(payload)
    entry = root.find("atom:entry", namespace)
    if entry is None:
        raise ResolutionError("arXiv returned no entry")
    identifier = (entry.findtext("atom:id", default="", namespaces=namespace) or "").strip()
    title = re.sub(
        r"\s+", " ", entry.findtext("atom:title", default="", namespaces=namespace) or ""
    )
    abstract = re.sub(
        r"\s+", " ", entry.findtext("atom:summary", default="", namespaces=namespace) or ""
    )
    published = entry.findtext("atom:published", default="", namespaces=namespace) or ""
    authors = [
        (author.findtext("atom:name", default="", namespaces=namespace) or "")
        for author in entry.findall("atom:author", namespace)
    ]
    arxiv_id = identifier.rsplit("/abs/", 1)[-1] if "/abs/" in identifier else identifier
    journal_ref = (
        entry.findtext("{http://arxiv.org/schemas/atom}journal_ref", default="", namespaces=None)
        or ""
    )
    doi_node = entry.find("{http://arxiv.org/schemas/atom}doi")
    doi = doi_node.text if doi_node is not None and doi_node.text else ""
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None
    return PaperMetadata(
        kind="arxiv",
        identifier=arxiv_id,
        title=title.strip(),
        doi=doi.strip(),
        year=int(published[:4]) if published[:4].isdigit() else None,
        journal=journal_ref.strip() or "arXiv",
        authors=[name for name in authors if name],
        abstract=abstract.strip(),
        pdf_url=pdf_url,
        landing_url=identifier or None,
        open_access=True,
        note="arXiv preprint",
    )


def parse_pubmed(payload: dict[str, Any], pmid: str) -> PaperMetadata:
    result = payload.get("result") or {}
    record: dict[str, Any] = result.get(pmid) or next(
        (value for key, value in result.items() if key.isdigit()), {}
    )
    if not record:
        raise ResolutionError(f"PubMed returned no record for {pmid}")
    doi = ""
    for article_id in record.get("articleids") or []:
        if article_id.get("idtype") == "doi":
            doi = str(article_id.get("value") or "")
            break
    authors = [
        author.get("name") or "" for author in (record.get("authors") or []) if author.get("name")
    ]
    pubdate = str(record.get("pubdate") or "")
    year = int(pubdate[:4]) if pubdate[:4].isdigit() else None
    return PaperMetadata(
        kind="pmid",
        identifier=pmid,
        title=str(record.get("title") or "").rstrip("."),
        doi=doi,
        year=year,
        journal=str(record.get("fulljournalname") or record.get("source") or ""),
        authors=authors,
        landing_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        note="PubMed record; PDF availability checked via PMC/Unpaywall",
    )


def parse_pmc_oa(payload: bytes) -> str | None:
    """PMC OA service: return a PDF link when the package is open."""
    root = ET.fromstring(payload)
    for link in root.iter("link"):
        fmt = (link.get("format") or "").lower()
        href = link.get("href") or ""
        if fmt == "pdf" and href:
            return href.replace("ftp://", "https://")
    return None


# ------------------------------------------------------------------ fetchers
def fetch_doi(doi: str, *, email: str = "", timeout: float = 20.0) -> PaperMetadata:
    payload = _get_json(f"{CROSSREF_API}/{urllib.parse.quote(doi)}", timeout=timeout)
    metadata = parse_crossref(payload, doi)
    if email:
        try:
            unpaywall = _get_json(
                f"{UNPAYWALL_API}/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}",
                timeout=timeout,
            )
            pdf_url, is_oa, note = parse_unpaywall(unpaywall)
            metadata.pdf_url = pdf_url
            metadata.open_access = is_oa
            metadata.note = note
        except ResolutionError as exc:
            metadata.note = f"Unpaywall unavailable: {exc}"
    else:
        metadata.note = "no contact email configured: open-access lookup skipped"
    return metadata


def fetch_arxiv(arxiv_id: str, *, timeout: float = 20.0) -> PaperMetadata:
    payload = _get(
        f"{ARXIV_API}?id_list={urllib.parse.quote(arxiv_id)}",
        timeout=timeout,
        accept="application/atom+xml",
    )
    return parse_arxiv(payload)


def fetch_pmid(pmid: str, *, email: str = "", timeout: float = 20.0) -> PaperMetadata:
    params = {"db": "pubmed", "id": pmid, "retmode": "json"}
    if email:
        params["email"] = email
    payload = _get_json(f"{PUBMED_ESUMMARY}?{urllib.parse.urlencode(params)}", timeout=timeout)
    metadata = parse_pubmed(payload, pmid)
    if metadata.doi:
        try:
            merged = fetch_doi(metadata.doi, email=email, timeout=timeout)
            metadata.pdf_url = merged.pdf_url
            metadata.open_access = merged.open_access
            metadata.note = merged.note
        except ResolutionError as exc:
            metadata.note = f"DOI resolution failed: {exc}"
    return metadata


def fetch_pmcid(pmcid: str, *, timeout: float = 20.0) -> PaperMetadata:
    payload = _get(f"{PMC_OA}?id={urllib.parse.quote(pmcid)}", timeout=timeout)
    pdf_url = parse_pmc_oa(payload)
    return PaperMetadata(
        kind="pmcid",
        identifier=pmcid,
        title="",
        pdf_url=pdf_url,
        open_access=pdf_url is not None,
        landing_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/",
        note="PMC open-access package" if pdf_url else "PMC: no open-access PDF link",
    )


def resolve(kind: str, identifier: str, *, email: str = "", timeout: float = 20.0) -> PaperMetadata:
    """Resolve any supported identifier to metadata plus a PDF URL when open access."""
    if kind == "doi":
        return fetch_doi(identifier, email=email, timeout=timeout)
    if kind == "arxiv":
        return fetch_arxiv(identifier, timeout=timeout)
    if kind == "pmid":
        return fetch_pmid(identifier, email=email, timeout=timeout)
    if kind == "pmcid":
        return fetch_pmcid(identifier, timeout=timeout)
    if kind == "url":
        return fetch_url(identifier)
    raise ResolutionError(f"cannot resolve source kind {kind!r}")


def fetch_url(url: str) -> PaperMetadata:
    """A bare URL is only a download location; no metadata is invented."""
    return PaperMetadata(
        kind="url",
        identifier=url,
        pdf_url=url if url.lower().endswith(".pdf") else None,
        landing_url=url,
        note="" if url.lower().endswith(".pdf") else "URL does not end in .pdf",
    )
