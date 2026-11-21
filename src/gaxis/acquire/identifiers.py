"""Identifier classification for service flow 2 (documents, DOIs, PubMed ids, URLs).

Deterministic and offline: deciding *what kind* of source the user handed over must
not depend on the network. Resolution (what the DOI points at) is M1's job.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_DOI_URL_RE = re.compile(r"^https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/\S+)$", re.IGNORECASE)
_ARXIV_RE = re.compile(r"^(arxiv:)?(\d{4}\.\d{4,5})(v\d+)?$", re.IGNORECASE)
_ARXIV_OLD_RE = re.compile(r"^(arxiv:)?([a-z\-]+(\.[A-Z]{2})?/\d{7})(v\d+)?$", re.IGNORECASE)
_PMID_RE = re.compile(r"^(pmid:|pubmed:)?(\d{6,9})$", re.IGNORECASE)
_PMCID_RE = re.compile(r"^pmc(\d+)$", re.IGNORECASE)
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


class SourceKind(StrEnum):
    pdf = "pdf"
    doi = "doi"
    arxiv = "arxiv"
    pmid = "pmid"
    pmcid = "pmcid"
    url = "url"
    unknown = "unknown"


NETWORK_KINDS = {
    SourceKind.doi,
    SourceKind.arxiv,
    SourceKind.pmid,
    SourceKind.pmcid,
    SourceKind.url,
}


def classify_source(source: str) -> SourceKind:
    """Classify without touching the network. Empty/whitespace is ``unknown``."""
    text = source.strip()
    if not text:
        return SourceKind.unknown
    path = Path(text).expanduser()
    if path.suffix.lower() == ".pdf":
        return SourceKind.pdf
    if _DOI_URL_RE.match(text):
        return SourceKind.doi
    if _DOI_RE.match(text):
        return SourceKind.doi
    if _ARXIV_RE.match(text) or _ARXIV_OLD_RE.match(text):
        return SourceKind.arxiv
    if _PMCID_RE.match(text):
        return SourceKind.pmcid
    if _PMID_RE.match(text):
        return SourceKind.pmid
    if _URL_RE.match(text):
        return SourceKind.url
    if path.exists() and path.is_file():
        return SourceKind.pdf if path.suffix.lower() == ".pdf" else SourceKind.unknown
    return SourceKind.unknown


def needs_network(kind: SourceKind) -> bool:
    return kind in NETWORK_KINDS


def normalise(source: str) -> str:
    """Strip wrappers so the same paper resolves to one id (``pmid:123`` -> ``123``)."""
    text = source.strip()
    match = _DOI_URL_RE.match(text)
    if match:
        return match.group(1)
    lowered = text.lower()
    for prefix in ("arxiv:", "pmid:", "pubmed:"):
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip()
    return text
