"""gbrain CLI adapter (subprocess bridge, verified in docs/gbrain-integration.md).

Why the CLI and not MCP: gbrain's PGLite datastore is single-writer and the CLI
already retries around it; a long-lived MCP client would hold a lock we do not need.
Every call is explicit, timeboxed and degradable — a missing brain must not take the
host's turn down with it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..config import KnowledgeSettings
from .base import KbError, KbHit, KbStatus


def resolve_binary(settings: KnowledgeSettings) -> str | None:
    if settings.binary:
        return settings.binary
    env = os.environ.get("GAXIS_GBRAIN_BIN")
    if env:
        return env
    found = shutil.which("gbrain")
    if found:
        return found
    repo_script = Path(__file__).resolve().parents[3] / "scripts" / "gbrain.sh"
    return str(repo_script) if repo_script.is_file() else None


class GbrainCLI:
    source = "paper-kb"

    def __init__(self, settings: KnowledgeSettings) -> None:
        self.settings = settings
        self.source = settings.source
        self.binary = resolve_binary(settings)
        self._env = dict(os.environ)
        if settings.gbrain_home:
            self._env["GBRAIN_HOME"] = settings.gbrain_home

    # ------------------------------------------------------------------ plumbing
    def _run(
        self, args: list[str], *, stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        if not self.binary:
            raise KbError("gbrain binary not found (set [knowledge] binary or install it)")
        try:
            completed = subprocess.run(  # noqa: S603 - argv built from our own values
                [self.binary, *args],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=self.settings.timeout_s,
                env=self._env,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise KbError(f"gbrain unavailable: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip().splitlines()[-3:]
            raise KbError(f"gbrain {' '.join(args[:2])} failed: {' | '.join(detail)}")
        return completed

    def _json(self, args: list[str], *, stdin: str | None = None) -> Any:
        completed = self._run(args, stdin=stdin)
        text = completed.stdout.strip()
        start = min(
            (pos for pos in (text.find("["), text.find("{")) if pos >= 0),
            default=-1,
        )
        if start > 0:
            text = text[start:]
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise KbError(f"gbrain returned non-JSON output: {text[:200]}") from exc

    # ---------------------------------------------------------------------- ops
    def put_page(self, slug: str, markdown: str, *, reason: str = "") -> dict[str, Any]:
        args = ["put", slug, "--force", "--content-origin", "tool_output"]
        if reason:
            args += ["--reason", reason[:400]]
        self._run(args, stdin=markdown)
        page = self.get_page(slug)
        if page is None:
            raise KbError(f"gbrain stored nothing for {slug}")
        return page

    def get_page(self, slug: str) -> dict[str, Any] | None:
        completed = self._run(["get", slug, "--json"])
        text = completed.stdout.strip()
        if not text:
            return None
        start = text.find("{")
        if start < 0:
            return None
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            return None

    def delete_page(self, slug: str) -> bool:
        try:
            self._run(["delete", slug, "--force"])
        except KbError:
            return False
        return True

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        types: list[str] | None = None,
        where: dict[str, str] | None = None,
    ) -> list[KbHit]:
        args = [
            "search",
            query,
            "--source-id",
            self.source,
            "--limit",
            str(max(limit, 1)),
            "--json",
        ]
        for page_type in types or []:
            args += ["--types", page_type]
        for key, value in (where or {}).items():
            args += ["--where", f"{key}={value}"]
        payload = self._json(args) or []
        if isinstance(payload, dict):  # tolerate a wrapped shape
            payload = payload.get("results") or payload.get("hits") or []
        hits: list[KbHit] = []
        for item in payload:
            if not isinstance(item, dict) or "slug" not in item:
                continue
            hits.append(
                KbHit(
                    slug=str(item["slug"]),
                    title=str(item.get("title") or ""),
                    score=float(item.get("score") or 0.0),
                    chunk_text=str(item.get("chunk_text") or ""),
                    page_type=str(item.get("type") or ""),
                    trust_tier=str(item.get("trust_tier") or ""),
                    source_id=str(item.get("source_id") or ""),
                )
            )
        return hits

    def status(self) -> KbStatus:
        try:
            health = self._json(["call", "get_health", "{}"]) or {}
        except KbError as exc:
            return KbStatus(available=False, source=self.source, message=str(exc))
        return KbStatus(
            available=True,
            source=self.source,
            pages=int(health.get("page_count") or 0),
            missing_embeddings=int(health.get("missing_embeddings") or 0),
            message="keyword search only" if not health.get("embed_coverage") else "",
            detail=health,
        )
