"""Local sandbox: same interface, no isolation — for development and tests.

It runs the script with the current interpreter (the pixi environment), so
matplotlib/numpy are available without building an image. The report states
explicitly that no isolation is enforced; a host must not treat a local run as
evidence of untrusted-code safety.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from .base import SandboxResult, SandboxSpec, collect_outputs


class LocalSandbox:
    engine = "local"

    def __init__(self, python: str | None = None) -> None:
        self.python = python or sys.executable

    def run(self, spec: SandboxSpec) -> SandboxResult:
        script = Path(spec.script)
        try:
            script_name = str(script.relative_to(spec.workdir))
        except ValueError:
            script_name = script.name
        env = dict(os.environ)
        env.update(
            {
                "MPLBACKEND": "Agg",
                "PYTHONHASHSEED": "0",
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "LANG": "C.UTF-8",
                **spec.env,
            }
        )
        # R scripts carry their interpreter in spec.command; python uses this env's python
        argv = list(spec.command) if spec.command else [self.python, script_name]
        started = time.time()
        try:
            completed = subprocess.run(
                argv,
                cwd=spec.workdir,
                capture_output=True,
                text=True,
                timeout=spec.timeout_s,
                env=env,
                check=False,
            )
            returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired:
            returncode, stdout, stderr = -9, "", f"timed out after {spec.timeout_s:g}s"
        duration = time.time() - started
        return SandboxResult(
            returncode=returncode,
            stdout=stdout[-20000:],
            stderr=stderr[-20000:],
            duration_s=duration,
            engine="local",
            outputs=collect_outputs(spec.workdir, started),
            report={
                "engine": "local",
                "network_enforced": False,
                "read_only_root": False,
                "duration_s": round(duration, 2),
                "warning": "no isolation: development engine, do not use for untrusted code",
            },
        )
