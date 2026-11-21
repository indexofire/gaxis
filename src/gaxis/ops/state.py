"""Checkpointed ingestion queue (M6 seed).

A paper crawl is a batch of independent sources; each one is a row, so a crash or a
network failure resumes where it stopped instead of restarting the batch. The queue is
SQLite under the data root — local, inspectable, and never part of the repository.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Job:
    source: str
    mode: str
    status: str
    attempts: int
    last_error: str
    manifest_ids: str
    updated_at: str
    kind: str = "ingest"


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    source TEXT PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'full',
    kind TEXT NOT NULL DEFAULT 'ingest',
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    manifest_ids TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
)
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class JobQueue:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(SCHEMA)
        columns = {
            row["name"] for row in self._connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "kind" not in columns:  # migration from the ingest-only queue
            self._connection.execute(
                "ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'ingest'"
            )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def enqueue(self, sources: list[str], *, mode: str = "full", kind: str = "ingest") -> int:
        added = 0
        for source in sources:
            cursor = self._connection.execute(
                "INSERT OR IGNORE INTO jobs (source, mode, kind, status, updated_at) "
                "VALUES (?, ?, ?, 'pending', ?)",
                (source, mode, kind, _now()),
            )
            added += cursor.rowcount
        self._connection.commit()
        return added

    def next_pending(self, limit: int = 5) -> list[Job]:
        rows = self._connection.execute(
            "SELECT * FROM jobs WHERE status = 'pending' ORDER BY updated_at LIMIT ?", (limit,)
        ).fetchall()
        return [Job(**dict(row)) for row in rows]

    def mark_running(self, source: str) -> None:
        self._connection.execute(
            "UPDATE jobs SET status='running', attempts=attempts+1, updated_at=? WHERE source=?",
            (_now(), source),
        )
        self._connection.commit()

    def mark_done(self, source: str, manifest_ids: list[str]) -> None:
        self._connection.execute(
            "UPDATE jobs SET status='done', last_error='', manifest_ids=?, updated_at=? "
            "WHERE source=?",
            (",".join(manifest_ids), _now(), source),
        )
        self._connection.commit()

    def mark_failed(self, source: str, error: str, *, retry: bool) -> None:
        status = "pending" if retry else "failed"
        self._connection.execute(
            "UPDATE jobs SET status=?, last_error=?, updated_at=? WHERE source=?",
            (status, error[:500], _now(), source),
        )
        self._connection.commit()

    def reclaim_stale(self, older_than_minutes: int = 30) -> int:
        """Return jobs stuck in ``running`` (a killed process) to the queue."""
        cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
        cursor = self._connection.execute(
            "UPDATE jobs SET status='pending', last_error='run stalled; reclaimed', updated_at=? "
            "WHERE status='running' AND updated_at < ?",
            (_now(), cutoff.isoformat(timespec="seconds")),
        )
        self._connection.commit()
        return cursor.rowcount

    def requeue(self, source: str, reason: str) -> None:
        self._connection.execute(
            "UPDATE jobs SET status='pending', last_error=?, updated_at=? WHERE source=?",
            (reason[:500], _now(), source),
        )
        self._connection.commit()

    def reset(self, source: str | None = None) -> int:
        if source and source != "all":
            cursor = self._connection.execute(
                "UPDATE jobs SET status='pending', last_error='', updated_at=? WHERE source=?",
                (_now(), source),
            )
        else:
            cursor = self._connection.execute(
                "UPDATE jobs SET status='pending', last_error='', updated_at=? "
                "WHERE status='failed'",
                (_now(),),
            )
        self._connection.commit()
        return cursor.rowcount

    def status(self) -> dict[str, int]:
        rows = self._connection.execute(
            "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
        ).fetchall()
        return {row["status"]: row["count"] for row in rows}

    def jobs(self) -> list[Job]:
        rows = self._connection.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()
        return [Job(**dict(row)) for row in rows]
