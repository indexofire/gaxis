"""Ingest manifests into the knowledge base, idempotently.

State lives in ``data/kb/state.json``: page slug -> content hash. Re-ingesting an
unchanged asset is a no-op; a re-validated asset (say L2 -> L1) produces a new hash
and is written over the old page. That keeps ``put`` cheap and makes the brain a
projection of the manifests rather than a second source of truth.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models.paper import ChartReproManifest
from .base import KbError, KnowledgeBase
from .pages import build_page


@dataclass
class IngestSummary:
    source: str
    upserted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unavailable: str = ""

    @property
    def ok(self) -> bool:
        return not self.unavailable and not self.failed

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "upserted": self.upserted,
            "skipped": self.skipped,
            "failed": [{"asset": asset, "error": error} for asset, error in self.failed],
            "removed": self.removed,
            "unavailable": self.unavailable,
            "counts": {
                "upserted": len(self.upserted),
                "skipped": len(self.skipped),
                "failed": len(self.failed),
                "removed": len(self.removed),
            },
        }

    def message(self) -> str:
        if self.unavailable:
            return f"knowledge base unavailable: {self.unavailable}"
        removed = f", {len(self.removed)} removed" if self.removed else ""
        return (
            f"knowledge base: {len(self.upserted)} upserted, {len(self.skipped)} unchanged, "
            f"{len(self.failed)} failed{removed}"
        )


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class KbIngestor:
    def __init__(self, kb: KnowledgeBase, *, state_path: Path) -> None:
        self.kb = kb
        self.state_path = state_path

    def ingest(
        self, manifests: Iterable[ChartReproManifest], *, force: bool = False
    ) -> IngestSummary:
        state = _load_state(self.state_path)
        summary = IngestSummary(source=self.kb.source)
        for manifest in manifests:
            slug, markdown = build_page(manifest, source=self.kb.source)
            content_sha = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
            previous = state.get(slug, {})
            if not force and previous.get("content_sha") == content_sha:
                summary.skipped.append(manifest.manifest_id)
                continue
            try:
                page = self.kb.put_page(
                    slug, markdown, reason=f"gaxis ingest {manifest.manifest_id}"
                )
            except KbError as exc:
                if "not found" in str(exc) or "unavailable" in str(exc):
                    summary.unavailable = str(exc)
                    summary.failed.append((manifest.manifest_id, str(exc)))
                else:
                    summary.failed.append((manifest.manifest_id, str(exc)))
                continue
            state[slug] = {
                "content_sha": content_sha,
                "revision": page.get("revision"),
                "asset_id": manifest.manifest_id,
                "ingested_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            summary.upserted.append(manifest.manifest_id)
        _save_state(self.state_path, state)
        return summary

    def forget(self, manifest_ids: Iterable[str]) -> list[str]:
        state = _load_state(self.state_path)
        removed: list[str] = []
        for manifest_id in manifest_ids:
            slug = f"{self.kb.source}:{manifest_id.replace('/', '-').replace(' ', '-')}"
            if slug in state and self.kb.delete_page(slug):
                state.pop(slug, None)
                removed.append(manifest_id)
        _save_state(self.state_path, state)
        return removed
