"""Analysis recipe results (table -> table), separate from figure manifests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .. import __version__


class AmrCooccurrenceParams(BaseModel):
    min_prevalence: float = Field(default=0.05, ge=0.0, le=1.0)
    min_support: int = Field(default=2, ge=1)
    weight: Literal["jaccard", "count"] = "jaccard"


class AnalysisRun(BaseModel):
    run_id: str
    recipe: str
    version: str = "amr-cooccurrence-v1"
    input_path: str
    input_sha256: str
    params: dict[str, Any]
    samples: int
    genes: int
    edges: int
    outputs: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tool: str = f"gaxis {__version__}"
