"""Script execution. Local process now; the container sandbox sits behind the same call."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: str
    stderr: str
    duration_s: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def interpreter(backend: str) -> list[str]:
    if backend == "python":
        return [sys.executable]
    rscript = shutil.which("Rscript")
    if not rscript:
        raise FileNotFoundError("Rscript not found; install R or use the python backend")
    return [rscript, "--vanilla"]


def run_script(
    script: Path, *, cwd: Path, timeout_s: float = 180.0, backend: str = "python"
) -> ExecResult:
    argv = [*interpreter(backend), str(script)]
    env = dict(os.environ)
    env.update(
        {
            "MPLBACKEND": "Agg",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            # Keep locale-dependent sorting deterministic across hosts.
            "PYTHONHASHSEED": "0",
        }
    )
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ExecResult(
            returncode=-9,
            stdout="",
            stderr=f"timeout after {timeout_s:g}s",
            duration_s=time.perf_counter() - started,
        )
    return ExecResult(
        returncode=completed.returncode,
        stdout=completed.stdout[-8000:],
        stderr=completed.stderr[-8000:],
        duration_s=time.perf_counter() - started,
    )
