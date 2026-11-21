"""Run the ingestion queue with checkpoints and bounded retries."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..errors import GaxisError
from ..models.tools import IngestPaperRequest
from ..service import ingest_paper, load_manifest
from .state import JobQueue


@dataclass
class RunSummary:
    processed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    reclaimed: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "processed": self.processed,
            "failed": [{"source": source, "error": error} for source, error in self.failed],
            "skipped": self.skipped,
            "reclaimed": self.reclaimed,
        }


def run_queue(
    queue: JobQueue,
    *,
    limit: int = 5,
    retries: int = 2,
    stall_minutes: int = 30,
) -> RunSummary:
    """Drain up to ``limit`` pending jobs. Each job is its own checkpoint."""
    started = time.perf_counter()
    summary = RunSummary()
    summary.reclaimed = queue.reclaim_stale(stall_minutes)
    for job in queue.next_pending(limit):
        if job.status == "done":  # defensive: the query already filters
            summary.skipped.append(job.source)
            continue
        queue.mark_running(job.source)
        if job.kind == "reproduce":
            _run_reproduce_job(queue, job, summary)
            continue
        try:
            result = ingest_paper(
                IngestPaperRequest(source=job.source, mode=job.mode)  # type: ignore[arg-type]
            )
        except GaxisError as exc:
            can_retry = job.attempts < retries and exc.code in {
                "resolution_failed",
                "download_failed",
                "pdf_unreadable",
            }
            queue.mark_failed(job.source, f"{exc.code}: {exc.message}", retry=can_retry)
            summary.failed.append((job.source, exc.code))
            continue
        except Exception as exc:  # noqa: BLE001 - a batch must survive one bad source
            queue.mark_failed(job.source, f"{type(exc).__name__}: {exc}", retry=False)
            summary.failed.append((job.source, type(exc).__name__))
            continue
        queue.mark_done(job.source, result.manifest_ids)
        summary.processed.append(job.source)
    _write_heartbeat(queue.path.parent / "heartbeat.json", summary, queue.status(), started)
    return summary


def _run_reproduce_job(queue: JobQueue, job: object, summary: RunSummary) -> None:
    """Reproduce every suitable figure of one paper, then checkpoint the outcome."""
    from ..config import settings
    from .state import Job

    if not isinstance(job, Job):  # pragma: no cover - typed call site
        return
    from ..repro.batch import reproduce_paper

    try:
        batch = reproduce_paper(
            job.source,
            manifests_dir=settings().manifests_dir,
            engine=None,
        )
    except GaxisError as exc:
        queue.mark_failed(job.source, f"{exc.code}: {exc.message}", retry=False)
        summary.failed.append((job.source, exc.code))
        return
    reproduced = batch.manifest_ids(("reproduced",))
    if not reproduced:
        graded = [
            item
            for item in batch.items
            if item.status == "skipped" and "already graded" in item.reason
        ]
        if graded and len(graded) == len(batch.items):
            queue.mark_done(job.source, [item.manifest_id for item in graded])
            summary.skipped.append(job.source)
            return
        reasons = "; ".join(
            f"{item.manifest_id}: {item.status} {item.reason}".strip() for item in batch.items[:3]
        )
        queue.mark_failed(job.source, reasons or "nothing reproduced", retry=False)
        summary.failed.append((job.source, "nothing_reproduced"))
        return
    queue.mark_done(job.source, reproduced)
    summary.processed.append(job.source)


def _write_heartbeat(
    path: Path, summary: RunSummary, state: dict[str, int], started: float
) -> None:
    payload = {
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "duration_s": round(time.perf_counter() - started, 2),
        "processed": summary.processed,
        "failed": [source for source, _ in summary.failed],
        "reclaimed": summary.reclaimed,
        "queue": state,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@dataclass
class VerifySummary:
    checked: int = 0
    missing: int = 0
    requeued: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "checked": self.checked,
            "missing": self.missing,
            "requeued": self.requeued,
        }


def verify_queue(queue: JobQueue, manifests_dir: Path) -> VerifySummary:
    """Deep check: a `done` job whose manifests vanished is not actually done.

    The knowledge base is rebuildable, but a manifest is evidence. If the evidence is
    gone (cleaned data dir, failed backup restore), the source is requeued and the
    reason is recorded instead of leaving a false `done`.
    """
    summary = VerifySummary()
    for job in queue.jobs():
        if job.status != "done":
            continue
        summary.checked += 1
        ids = [item for item in job.manifest_ids.split(",") if item]
        missing = [item for item in ids if load_manifest(item, manifests_dir) is None]
        if missing:
            summary.missing += len(missing)
            queue.requeue(job.source, "evidence missing: " + ", ".join(missing[:3]))
            summary.requeued.append(job.source)
    return summary
