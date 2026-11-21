"""Bounded PDF download: magic check, size cap, HTML rejection (no network)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from gaxis.acquire import download
from gaxis.acquire.download import download_pdf, is_pdf
from gaxis.acquire.metadata import ResolutionError


class _FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, content_type: str) -> None:
        super().__init__(payload)
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch(monkeypatch: pytest.MonkeyPatch, payload: bytes, content_type: str) -> None:
    monkeypatch.setattr(
        download.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(payload, content_type),
    )


def test_valid_pdf_is_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, b"%PDF-1.7\nrest of file", "application/pdf")
    target = download_pdf("https://example.org/x.pdf", tmp_path, identifier="10.1/x")
    assert target.is_file()
    assert is_pdf(target)
    assert target.read_bytes().startswith(b"%PDF-")


def test_html_is_rejected_with_a_clear_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, b"<html>paywall</html>", "text/html")
    with pytest.raises(ResolutionError, match="HTML"):
        download_pdf("https://example.org/x", tmp_path, identifier="a")


def test_oversized_download_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, b"%PDF-" + b"0" * 4096, "application/pdf")
    with pytest.raises(ResolutionError, match="limit"):
        download_pdf("https://example.org/x.pdf", tmp_path, identifier="b", max_mb=0.001)


def test_cached_file_is_reused_without_a_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cached = tmp_path / "cached.pdf"
    cached.write_bytes(b"%PDF-1.4" + b"x" * 2048)
    monkeypatch.setattr(
        download.urllib.request, "urlopen", lambda *a, **k: pytest.fail("should not fetch")
    )
    target = download_pdf("https://example.org/x.pdf", tmp_path, identifier="cached")
    assert target == cached


def test_is_pdf_rejects_non_pdf(tmp_path: Path) -> None:
    text = tmp_path / "t.bin"
    text.write_bytes(b"not a pdf at all")
    assert is_pdf(text) is False
    assert is_pdf(tmp_path / "missing.bin") is False
