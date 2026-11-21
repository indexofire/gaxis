"""Selection feedback: which knowledge-base asset a user actually chose.

Ranking is calibrated against real choices, not only against a golden set. Every time a
figure is rendered *from* an asset (or adapted from one), the choice is appended to a
JSONL log under the data root. The log is append-only and local; it never blocks a render,
but a failed write is logged rather than swallowed.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def selection_log_path(data_root: Path) -> Path:
    return data_root / "kb" / "selections.jsonl"


def record_selection(
    data_root: Path,
    *,
    asset_id: str,
    action: str,
    figure_id: str = "",
    preset: str = "",
    chart_type: str = "",
    note: str = "",
) -> str | None:
    """Append one choice; returns the log path, or None when the write failed."""
    path = selection_log_path(data_root)
    entry = {
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "asset_id": asset_id,
        "action": action,
        "figure_id": figure_id,
        "preset": preset,
        "chart_type": chart_type,
        "note": note,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError as exc:
        logger.warning("selection feedback not recorded for %s: %s", asset_id, exc)
        return None
    return str(path)
