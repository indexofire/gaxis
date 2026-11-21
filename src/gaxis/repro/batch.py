"""Batch reproduction: "reproduce the suitable figures of this paper".

Suitability is explicit: a figure needs a code candidate at or above
``min_confidence`` and a runnable input. Missing input is reported as ``needs_data``
(optionally satisfied with clearly labelled synthetic data), never as a success.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import GaxisError
from ..models.paper import ChartReproManifest
from ..models.tools import ReproduceChartCodeRequest
from .synthetic import generate_csv

logger = logging.getLogger(__name__)

DATA_ERROR_MARKERS = (
    "filenotfound",
    "no such file",
    "cannot open",
    "does not exist",
    "could not find",
    "cannot find",
)


@dataclass(frozen=True)
class BatchItem:
    manifest_id: str
    status: str
    level: str = "none"
    reason: str = ""
    data_source: str = "none"


@dataclass
class BatchSummary:
    paper_id: str
    items: list[BatchItem] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "paper_id": self.paper_id,
            "items": [item.__dict__ for item in self.items],
            "counts": {
                status: sum(1 for item in self.items if item.status == status)
                for status in ("reproduced", "needs_data", "needs_env", "skipped", "failed")
            },
        }

    def manifest_ids(self, statuses: tuple[str, ...] = ("reproduced",)) -> list[str]:
        return [item.manifest_id for item in self.items if item.status in statuses]


def _manifests_for(paper_id: str, manifests_dir: Path) -> list[ChartReproManifest]:
    manifests: list[ChartReproManifest] = []
    if not manifests_dir.is_dir():
        return manifests
    for path in sorted(manifests_dir.glob("*.json")):
        try:
            manifest = ChartReproManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - an unreadable manifest must not stop the batch
            logger.warning("skipping unreadable manifest %s: %s", path.name, exc)
            continue
        if manifest.paper_id == paper_id:
            manifests.append(manifest)
    return manifests


def _suitability(manifest: ChartReproManifest) -> tuple[float, str]:
    """Best code candidate confidence and why it is (not) suitable."""
    if not manifest.code_candidates:
        return 0.0, "no code candidate attached"
    best = max(manifest.code_candidates, key=lambda item: item.pairing_confidence)
    if not Path(best.code_path).is_file():
        return 0.0, f"code file is missing: {best.code_path}"
    return best.pairing_confidence, ""


def reproduce_paper(
    paper_id: str,
    *,
    manifests_dir: Path,
    data_path: Path | None = None,
    min_confidence: float = 0.5,
    limit: int = 8,
    engine: str | None = None,
    synthetic: bool = False,
    force: bool = False,
    timeout_s: float | None = None,
    synthetic_dir: Path | None = None,
) -> BatchSummary:
    from .. import service
    from ..config import settings

    conf = settings()
    summary = BatchSummary(paper_id=paper_id)
    manifests = _manifests_for(paper_id, manifests_dir)
    if not manifests:
        raise GaxisError(
            "manifest_not_found",
            f"no figures recorded for paper {paper_id!r}",
            hint="run `gaxis ingest <paper>` first",
        )
    if data_path is not None and not data_path.is_file():
        raise GaxisError("data_not_found", f"input data not found: {data_path}")
    ordered = sorted(
        manifests,
        key=lambda manifest: (
            manifest.reproduction.level in {"L1", "L2"},
            -(manifest.usefulness.score if manifest.usefulness else 0.0),
        ),
    )
    target_dir = synthetic_dir or (conf.data_root / "synthetic")
    processed = 0
    for manifest in ordered:
        if processed >= limit:
            break
        if manifest.reproduction.level in {"L1", "L2"} and not force:
            summary.items.append(
                BatchItem(
                    manifest.manifest_id, "skipped", manifest.reproduction.level, "already graded"
                )
            )
            continue
        confidence, problem = _suitability(manifest)
        if problem:
            summary.items.append(BatchItem(manifest.manifest_id, "skipped", reason=problem))
            continue
        if confidence < min_confidence:
            summary.items.append(
                BatchItem(
                    manifest.manifest_id,
                    "skipped",
                    reason=f"code pairing confidence {confidence:.2f} < {min_confidence:.2f}",
                )
            )
            continue
        candidate = max(manifest.code_candidates, key=lambda item: item.pairing_confidence)
        chosen_data = data_path
        source = "user" if data_path else "none"
        if chosen_data is None and synthetic:
            from .synthetic import infer_columns

            columns = infer_columns(Path(candidate.code_path))
            stamp = manifest.manifest_id.replace("/", "__")
            chosen_data = generate_csv(columns, target_dir / f"{stamp}.csv", seed=manifest.caption)
            source = "synthetic"
        processed += 1
        try:
            result = service.reproduce_chart_code(
                ReproduceChartCodeRequest(
                    manifest_id=manifest.manifest_id,
                    code_path=candidate.code_path,
                    data_path=str(chosen_data) if chosen_data else None,
                    engine=engine,  # type: ignore[arg-type]
                    timeout_s=timeout_s or 300,
                )
            )
        except GaxisError as exc:
            summary.items.append(
                BatchItem(manifest.manifest_id, "failed", reason=f"{exc.code}: {exc.message}")
            )
            continue
        reason = result.failure_reason
        notes = " ".join(str(note) for note in result.sandbox_report.get("notes", []))
        status = "reproduced" if result.run_status == "success" else "failed"
        if result.engine == "local":
            reason = (reason + "; " if reason else "") + (
                "ran on the local engine (no podman image): not evidence of safe execution"
            )
        elif "image not ready" in notes:
            status = "needs_env"
            reason = "sandbox image unavailable: " + notes[-160:]
        if (
            status == "failed"
            and result.run_status == "failed"
            and chosen_data is None
            and any(marker in reason.lower() for marker in DATA_ERROR_MARKERS)
        ):
            status = "needs_data"
            reason = "the script needs an input table; pass --data or --synthetic"
        summary.items.append(
            BatchItem(
                manifest.manifest_id,
                status,
                level=result.level,
                reason=reason,
                data_source=source,
            )
        )
    return summary


def reproduce_paper_with_summary(
    paper_id: str, **kwargs: object
) -> tuple[BatchSummary, Path | None]:
    """Batch reproduction plus the JSON report location (ops queue uses this)."""
    summary = reproduce_paper(paper_id, **kwargs)  # type: ignore[arg-type]
    return summary, None
