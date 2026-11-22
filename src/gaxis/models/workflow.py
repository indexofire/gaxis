"""Workflow recipe scaffold (Snakemake) — generated, not executed by the kernel."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from .. import __version__


class WorkflowScaffold(BaseModel):
    workflow_id: str
    version: str
    out_dir: str
    engine: Literal["snakemake"] = "snakemake"
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    container: str = ""
    check: str = ""
    tool: str = f"gaxis {__version__}"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
