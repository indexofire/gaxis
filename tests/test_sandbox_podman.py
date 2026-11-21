"""Podman mechanics: isolation flags, mounts, outputs, network blocking, timeouts.

Skipped when podman or the reproduction image is absent — these tests must never
silently pass, and they must never build an image (build is a setup step, not a test).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from gaxis.sandbox.base import Mount, SandboxSpec
from gaxis.sandbox.image import image_exists
from gaxis.sandbox.podman import PodmanSandbox, podman_available

IMAGE = "gaxis-repro:py312"
R_IMAGE = "gaxis-repro-r:4.5"
r_available = podman_available() and image_exists(R_IMAGE)

pytestmark = pytest.mark.skipif(
    not podman_available() or not image_exists(IMAGE),
    reason="podman or the gaxis-repro image is not available",
)

SCRIPT = """\
import os
import socket
from pathlib import Path

Path("out.png").write_bytes(b"hello")
Path("summary.txt").write_text("mounts=" + str(sorted(os.listdir('/data'))) + "\\n")
try:
    socket.create_connection(("1.1.1.1", 80), timeout=3)
    print("NETWORK: reachable")
except OSError as exc:
    print("NETWORK: blocked", type(exc).__name__)
try:
    Path("/etc/passwd").write_text("nope")
    print("ROOT: writable")
except OSError:
    print("ROOT: read-only")
"""


def _spec(tmp_path: Path, *, network: bool = False, timeout_s: float = 60) -> SandboxSpec:
    workdir = tmp_path / "work"
    workdir.mkdir()
    script = workdir / "probe.py"
    script.write_text(SCRIPT)
    data = tmp_path / "data"
    data.mkdir()
    (data / "input.csv").write_text("a,b\n1,2\n")
    return SandboxSpec(
        script=script,
        workdir=workdir,
        mounts=(Mount(source=data, target="/data", read_only=True),),
        timeout_s=timeout_s,
        network=network,
        image=IMAGE,
    )


def test_run_isolated_writes_outputs_and_blocks_network(tmp_path: Path) -> None:
    result = PodmanSandbox(image=IMAGE).run(_spec(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "NETWORK: blocked" in result.stdout
    assert "ROOT: read-only" in result.stdout
    names = {path.name for path in result.outputs}
    assert {"out.png", "summary.txt"} <= names
    summary = (tmp_path / "work" / "summary.txt").read_text()
    assert "input.csv" in summary
    assert result.report["network_enforced"] is True
    assert result.report["read_only_root"] is True
    assert result.report["image"] == IMAGE


def test_timeout_kills_the_container(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    script = workdir / "slow.py"
    script.write_text("import time\ntime.sleep(60)\n")
    result = PodmanSandbox(image=IMAGE).run(
        SandboxSpec(script=script, workdir=workdir, timeout_s=3, image=IMAGE)
    )
    assert result.returncode == -9
    assert "timed out" in result.stderr


def test_matplotlib_render_inside_the_sandbox(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    script = workdir / "figure.py"
    script.write_text(
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots(figsize=(2, 1.2))\n"
        "ax.bar(['A', 'B'], [3, 5])\n"
        "fig.savefig('figure.png', dpi=300)\n"
        "print('rendered')\n"
    )
    result = PodmanSandbox(image=IMAGE).run(
        SandboxSpec(script=script, workdir=workdir, timeout_s=120, image=IMAGE)
    )
    assert result.returncode == 0, result.stderr
    pngs = [path for path in result.outputs if path.suffix == ".png"]
    assert pngs
    assert pngs[0].stat().st_size > 1000


def test_missing_workdir_mount_fails_loudly(tmp_path: Path) -> None:
    if shutil.which("podman") is None:  # pragma: no cover - guarded by pytestmark
        pytest.skip("podman missing")
    spec = _spec(tmp_path)
    missing = SandboxSpec(
        script=spec.script,
        workdir=spec.workdir,
        mounts=(Mount(source=tmp_path / "does-not-exist", target="/nope"),),
        timeout_s=30,
        image=IMAGE,
    )
    result = PodmanSandbox(image=IMAGE).run(missing)
    assert result.returncode != 0
    assert result.stderr


@pytest.mark.skipif(not r_available, reason="R reproduction image is not available")
def test_r_image_renders_ggplot(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    script = workdir / "figure.R"
    script.write_text(
        "suppressPackageStartupMessages(library(ggplot2))\n"
        "p <- ggplot(data.frame(g = c('A', 'B'), y = c(3, 5)), aes(g, y)) + geom_col()\n"
        "ggsave('figure.png', p, width = 60, height = 40, units = 'mm', dpi = 300)\n"
        "cat('rendered\\n')\n"
    )
    result = PodmanSandbox().run(
        SandboxSpec(
            script=script,
            workdir=workdir,
            timeout_s=180,
            image=R_IMAGE,
            command=("Rscript", "figure.R"),
        )
    )
    assert result.returncode == 0, result.stderr
    assert "rendered" in result.stdout
    pngs = [path for path in result.outputs if path.suffix == ".png"]
    assert pngs
    assert pngs[0].stat().st_size > 1000
    assert result.report["image"] == R_IMAGE
