"""Result of LLM-assisted reconstruction (CLI/service, not part of the MCP contract)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .manifest import OutputFile


class ReconstructResult(BaseModel):
    manifest_id: str
    method: str = "llm_reconstruction"
    level: str = "none"
    visual_similarity: float | None = None
    rounds: int = 0
    similarity_history: list[float] = Field(default_factory=list)
    outputs: list[OutputFile] = Field(default_factory=list)
    code_path: str = ""
    code_sha256: str = ""
    data_path: str = ""
    data_source: str = "none"
    engine: str = "none"
    model: str | None = None
    failure_reason: str = ""
    manifest_path: str = ""
    kb_refresh: str = ""
