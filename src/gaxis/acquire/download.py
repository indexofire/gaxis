"""Downloading open-access PDFs, with explicit limits.

Downloads are untrusted input: size-capped, content-checked, written atomically, and
cached by identifier so a retry does not re-fetch. Nothing is unzipped or executed.
"""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .metadata import USER_AGENT, ResolutionError

_PDF_MAGIC = b"%PDF-"


def _safe_name(identifier: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", identifier).strip("_")
    return cleaned[:80] or hashlib.sha256(identifier.encode()).hexdigest()[:12]


def download_pdf(
    url: str,
    dest_dir: Path,
    *,
    identifier: str = "",
    max_mb: float = 40.0,
    timeout: float = 60.0,
) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{_safe_name(identifier or url)}.pdf"
    if target.is_file() and target.stat().st_size > 1024 and target.read_bytes()[:5] == _PDF_MAGIC:
        return target
    request = urllib.request.Request(  # noqa: S310 - caller supplies an https URL
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/pdf"},
    )
    limit = int(max_mb * 1024 * 1024)
    partial = target.with_suffix(".part")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            content_type = response.headers.get("Content-Type", "")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > limit:
                raise ResolutionError(
                    f"PDF is {int(declared) / 1e6:.1f} MB, above the {max_mb:g} MB limit"
                )
            head = response.read(5)
            if not head.startswith(_PDF_MAGIC):
                if "html" in content_type.lower() or head[:1] == b"<":
                    raise ResolutionError(
                        "the URL returned HTML, not a PDF (paywall or landing page)"
                    )
                raise ResolutionError(f"unexpected content type {content_type!r}")
            written = 0
            with partial.open("wb") as handle:
                handle.write(head)
                written += len(head)
                while chunk := response.read(1 << 16):
                    written += len(chunk)
                    if written > limit:
                        raise ResolutionError(f"PDF exceeds the {max_mb:g} MB limit")
                    handle.write(chunk)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        partial.unlink(missing_ok=True)
        raise ResolutionError(f"download failed for {url}: {exc}") from exc
    except ResolutionError:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(target)
    return target


def is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(5).startswith(_PDF_MAGIC)
    except OSError:
        return False


def parse_filename_url(url: str) -> str | None:
    """Best-effort PDF URL from a landing page URL (used only as a hint)."""
    parsed = urllib.parse.urlparse(url)
    if parsed.path.lower().endswith(".pdf"):
        return url
    return None
