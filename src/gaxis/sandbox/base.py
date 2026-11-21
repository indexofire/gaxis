"""Sandbox port: run untrusted paper code with isolation and a reproducible report.

Two implementations: ``PodmanSandbox`` (production, ADR-11) and ``LocalSandbox``
(development/tests). Both return the same ``SandboxResult`` so the grading code
never branches on the engine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Mount:
    source: Path
    target: str
    read_only: bool = True


@dataclass(frozen=True)
class SandboxSpec:
    """What to run and under which limits."""

    script: Path
    workdir: Path
    mounts: tuple[Mount, ...] = ()
    timeout_s: float = 300.0
    network: bool = False
    image: str = "gaxis-repro:py312"
    memory: str = "4g"
    cpus: float = 2.0
    pids_limit: int = 256
    env: dict[str, str] = field(default_factory=dict)
    command: tuple[str, ...] = ()


@dataclass
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    engine: str
    outputs: list[Path] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def tail(self, lines: int = 12) -> str:
        text = (self.stderr or self.stdout).strip().splitlines()
        return "\n".join(text[-lines:])


class Sandbox(Protocol):
    engine: str

    def run(self, spec: SandboxSpec) -> SandboxResult: ...


def collect_outputs(workdir: Path, started: float) -> list[Path]:
    """Files the script produced (ignore the script itself and caches)."""
    outputs: list[Path] = []
    for path in sorted(workdir.rglob("*")):
        if not path.is_file() or path.stat().st_mtime < started - 2:
            continue
        if "__pycache__" in path.parts or path.suffix in {".py", ".pyc"}:
            continue
        outputs.append(path)
    return outputs


def now() -> float:
    return time.time()
