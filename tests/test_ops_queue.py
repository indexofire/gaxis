"""Checkpointed ingestion queue."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaxis.errors import GaxisError
from gaxis.ops.runner import run_queue
from gaxis.ops.state import JobQueue
from gaxis.service import IngestPaperResult


def _queue(tmp_path: Path) -> JobQueue:
    return JobQueue(tmp_path / "ops" / "queue.db")


def test_enqueue_is_idempotent(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    assert queue.enqueue(["10.1/a", "10.1/b"]) == 2
    assert queue.enqueue(["10.1/a", "10.1/c"]) == 1
    queue.close()


def test_run_processes_and_checkpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    queue = _queue(tmp_path)
    queue.enqueue(["10.1/a", "10.1/b"])
    calls: list[str] = []

    def fake_ingest(request):
        calls.append(request.source)
        return IngestPaperResult(paper_id="pdf-1", manifest_ids=[f"{request.source}/fig-1"])

    monkeypatch.setattr("gaxis.ops.runner.ingest_paper", fake_ingest)
    summary = run_queue(queue, limit=10)
    assert summary.processed == ["10.1/a", "10.1/b"]
    assert queue.status() == {"done": 2}
    assert "10.1/a/fig-1" in queue.jobs()[0].manifest_ids

    # a second run does not redo finished work
    monkeypatch.setattr("gaxis.ops.runner.ingest_paper", lambda request: pytest.fail("rerun"))
    assert run_queue(queue, limit=10).processed == []
    queue.close()


def test_transient_failure_is_retried_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = _queue(tmp_path)
    queue.enqueue(["10.1/flaky"])
    attempts = {"count": 0}

    def flaky(request):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise GaxisError("download_failed", "network hiccup")
        return IngestPaperResult(paper_id="pdf-2", manifest_ids=["pdf-2/fig-1"])

    monkeypatch.setattr("gaxis.ops.runner.ingest_paper", flaky)
    first = run_queue(queue, limit=10, retries=2)
    assert first.failed
    assert queue.status() == {"pending": 1}
    second = run_queue(queue, limit=10, retries=2)
    assert second.processed == ["10.1/flaky"]
    assert queue.status() == {"done": 1}
    queue.close()


def test_permanent_failure_stops_retrying(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    queue = _queue(tmp_path)
    queue.enqueue(["not a paper"])

    def broken(request):
        raise GaxisError("unrecognised_source", "cannot classify")

    monkeypatch.setattr("gaxis.ops.runner.ingest_paper", broken)
    run_queue(queue, limit=10, retries=2)
    assert queue.status() == {"failed": 1}
    queue.reset("all")
    assert queue.status() == {"pending": 1}
    queue.close()


def test_stalled_run_is_reclaimed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    queue = _queue(tmp_path)
    queue.enqueue(["10.1/stuck"])
    queue.mark_running("10.1/stuck")
    assert queue.status() == {"running": 1}

    # A process that died mid-run leaves `running` behind; a later run must reclaim it.
    with queue._connection:  # test needs an old timestamp
        queue._connection.execute(
            "UPDATE jobs SET updated_at='2000-01-01T00:00:00+00:00' WHERE source='10.1/stuck'"
        )
    monkeypatch.setattr(
        "gaxis.ops.runner.ingest_paper",
        lambda request: IngestPaperResult(paper_id="pdf-9", manifest_ids=["pdf-9/fig-1"]),
    )
    summary = run_queue(queue, limit=5, stall_minutes=30)
    assert summary.reclaimed == 1
    assert summary.processed == ["10.1/stuck"]
    assert queue.status() == {"done": 1}
    queue.close()


def test_verify_requeues_jobs_with_missing_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gaxis.ops.runner import verify_queue

    queue = _queue(tmp_path)
    queue.enqueue(["10.1/gone"])
    monkeypatch.setattr(
        "gaxis.ops.runner.ingest_paper",
        lambda request: IngestPaperResult(paper_id="pdf-1", manifest_ids=["pdf-1/fig-1"]),
    )
    run_queue(queue, limit=5)
    assert queue.status() == {"done": 1}

    monkeypatch.setattr("gaxis.ops.runner.load_manifest", lambda manifest_id, folder: None)
    summary = verify_queue(queue, tmp_path / "manifests")
    assert summary.checked == 1
    assert summary.missing == 1
    assert summary.requeued == ["10.1/gone"]
    assert queue.status() == {"pending": 1}
    assert "evidence missing" in queue.jobs()[0].last_error
    queue.close()


def test_run_writes_heartbeat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    queue = _queue(tmp_path)
    queue.enqueue(["10.1/hb"])
    monkeypatch.setattr(
        "gaxis.ops.runner.ingest_paper",
        lambda request: IngestPaperResult(paper_id="pdf-3", manifest_ids=["pdf-3/fig-1"]),
    )
    run_queue(queue, limit=5)
    payload = json.loads((tmp_path / "ops" / "heartbeat.json").read_text())
    assert payload["processed"] == ["10.1/hb"]
    assert payload["queue"] == {"done": 1}
    assert payload["finished_at"]
    queue.close()
