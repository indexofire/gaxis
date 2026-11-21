"""Rootless podman sandbox (ADR-11): no network, read-only root, resource caps."""

from __future__ import annotations

import subprocess
import time
import uuid
from dataclasses import replace
from pathlib import Path

from .base import SandboxResult, SandboxSpec, collect_outputs

GUARD_ARGS = (
    "--security-opt",
    "no-new-privileges",
    "--cap-drop",
    "ALL",
    "--read-only",
    "--tmpfs",
    "/tmp:size=512m,mode=1777",
)


def podman_available() -> bool:
    import shutil

    return shutil.which("podman") is not None


def image_digest(image: str) -> str:
    try:
        completed = subprocess.run(
            ["podman", "image", "inspect", "--format", "{{.Id}}", image],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


class PodmanSandbox:
    engine = "podman"

    def __init__(self, *, image: str | None = None) -> None:
        self.image = image

    def build_command(self, spec: SandboxSpec, script_name: str) -> list[str]:
        name = f"gaxis-repro-{uuid.uuid4().hex[:10]}"
        argv = [
            "podman",
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "default" if spec.network else "none",
            "--memory",
            spec.memory,
            "--cpus",
            str(spec.cpus),
            "--pids-limit",
            str(spec.pids_limit),
            *GUARD_ARGS,
            "-w",
            "/work",
            "-v",
            f"{spec.workdir}:/work:rw",
        ]
        for mount in spec.mounts:
            mode = "ro" if mount.read_only else "rw"
            argv += ["-v", f"{mount.source}:{mount.target}:{mode}"]
        env = {
            "MPLBACKEND": "Agg",
            "HOME": "/tmp",
            "PYTHONHASHSEED": "0",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "LANG": "C.UTF-8",
            **spec.env,
        }
        for key, value in env.items():
            argv += ["-e", f"{key}={value}"]
        image = self.image or spec.image
        argv += [image, *(spec.command or ("python", script_name))]
        return argv

    def run(self, spec: SandboxSpec) -> SandboxResult:
        if not podman_available():
            raise FileNotFoundError("podman is not installed")
        script = Path(spec.script)
        try:
            script_name = str(script.relative_to(spec.workdir))
        except ValueError:
            script_name = script.name
        argv = self.build_command(spec, script_name)
        image = self.image or spec.image
        started = time.time()
        report: dict[str, object] = {
            "engine": "podman",
            "image": image,
            "image_id": image_digest(image),
            "network": spec.network,
            "memory": spec.memory,
            "cpus": spec.cpus,
            "pids_limit": spec.pids_limit,
            "read_only_root": True,
            "mounts": [{"target": m.target, "read_only": m.read_only} for m in spec.mounts],
            "network_enforced": True,
        }
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=spec.timeout_s,
                check=False,
            )
            returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired:
            _kill(argv)
            returncode, stdout, stderr = -9, "", f"timed out after {spec.timeout_s:g}s"
        duration = time.time() - started
        report["duration_s"] = round(duration, 2)
        report["command"] = " ".join(argv[:6]) + " …"
        return SandboxResult(
            returncode=returncode,
            stdout=stdout[-20000:],
            stderr=stderr[-20000:],
            duration_s=duration,
            engine="podman",
            outputs=collect_outputs(spec.workdir, started),
            report=report,
        )


def _kill(argv: list[str]) -> None:
    """Remove the container left behind by a timeout (``--rm`` never fires)."""
    try:
        name = argv[argv.index("--name") + 1]
    except (ValueError, IndexError):
        return
    subprocess.run(["podman", "rm", "-f", name], capture_output=True, timeout=60, check=False)


def with_network(spec: SandboxSpec, network: bool) -> SandboxSpec:
    return replace(spec, network=network)
