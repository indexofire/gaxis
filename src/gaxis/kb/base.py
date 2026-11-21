"""Knowledge-base port: the small surface gaxis needs from gbrain.

Keeping this a protocol means the KB can be faked in tests, replaced by a local
index, or pointed at a newer gbrain without touching service/ or plan logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class KbHit:
    slug: str
    title: str
    score: float
    chunk_text: str = ""
    page_type: str = ""
    trust_tier: str = ""
    source_id: str = ""


@dataclass(frozen=True)
class KbStatus:
    available: bool
    source: str
    pages: int = 0
    missing_embeddings: int = 0
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


class KbError(RuntimeError):
    """gbrain is missing, busy or returned garbage — callers degrade, never crash."""


class KnowledgeBase(Protocol):
    source: str

    def put_page(self, slug: str, markdown: str, *, reason: str = "") -> dict[str, Any]: ...

    def get_page(self, slug: str) -> dict[str, Any] | None: ...

    def delete_page(self, slug: str) -> bool: ...

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        types: list[str] | None = None,
        where: dict[str, str] | None = None,
    ) -> list[KbHit]: ...

    def status(self) -> KbStatus: ...


def try_get_page(kb: KnowledgeBase, slug: str) -> dict[str, Any] | None:
    """``get_page`` without treating "missing" as an error (gbrain exits non-zero)."""
    try:
        return kb.get_page(slug)
    except KbError:
        return None
