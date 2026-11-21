"""Reproduction image management: build once, pin by id, run offline afterwards.

A reproduction environment must be reproducible itself (plan C2). We start from a
pinned base image and install the figure stack at build time; every run records the
resolved image id, so a later change of ``matplotlib`` cannot silently change a
grading result.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .podman import image_digest, podman_available

R_INSTALL = (
    'RUN Rscript -e "install.packages(c({packages}), '
    "repos = 'https://cloud.r-project.org', Ncpus = 4)\""
)

CONTAINER_HEADER = """\
FROM {base}
ENV HOME=/tmp \\
    LANG=C.UTF-8
"""
PYTHON_STEP = """\
ENV MPLBACKEND=Agg \\
    PIP_NO_CACHE_DIR=1 \\
    PIP_DISABLE_PIP_VERSION_CHECK=1 \\
    PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir {packages}
"""
CONTAINER_FOOTER = """\
WORKDIR /work
"""


def render_containerfile(
    base: str, packages: list[str] | None, r_packages: list[str] | None
) -> str:
    """Python image (pip) or R image (CRAN binaries) — never both."""
    body = CONTAINER_HEADER.format(base=base)
    if packages:
        body += PYTHON_STEP.format(packages=" ".join(packages))
    if r_packages:
        quoted = ", ".join(f"'{name}'" for name in r_packages)
        body += R_INSTALL.format(packages=quoted) + "\n"
    return body + CONTAINER_FOOTER


BASE_IMAGE = "docker.io/library/python:3.12-slim"


def image_exists(image: str) -> bool:
    if not podman_available():
        return False
    completed = subprocess.run(
        ["podman", "image", "exists", image],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return completed.returncode == 0


def build_image(
    image: str,
    *,
    base: str = BASE_IMAGE,
    packages: list[str] | None = None,
    context_dir: Path,
    timeout_s: float = 900.0,
    r_packages: list[str] | None = None,
) -> tuple[bool, str]:
    """Build the reproduction image. Returns (ok, log tail)."""
    if not podman_available():
        return False, "podman is not installed"
    if not r_packages and packages is None:
        packages = ["matplotlib", "numpy"]
    if r_packages:
        packages = None
    context_dir.mkdir(parents=True, exist_ok=True)
    containerfile = context_dir / "Containerfile"
    containerfile.write_text(render_containerfile(base, packages, r_packages), encoding="utf-8")
    try:
        completed = subprocess.run(
            [
                "podman",
                "build",
                "--tag",
                image,
                "--file",
                str(containerfile),
                str(context_dir),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"image build timed out after {timeout_s:g}s"
    tail = "\n".join((completed.stdout + completed.stderr).strip().splitlines()[-8:])
    return completed.returncode == 0, tail


def pull_image(image: str, *, timeout_s: float = 900.0) -> tuple[bool, str]:
    """Pull a prebuilt image (used when no build steps are needed)."""
    try:
        completed = subprocess.run(
            ["podman", "pull", image],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"pull failed: {exc}"
    tail = "\n".join((completed.stdout + completed.stderr).strip().splitlines()[-4:])
    return completed.returncode == 0, tail


def ensure_image(
    image: str,
    *,
    autobuild: bool,
    packages: list[str] | None,
    context_dir: Path,
    base: str = BASE_IMAGE,
    r_packages: list[str] | None = None,
) -> tuple[bool, str]:
    """Make sure ``image`` exists; returns (ready, message)."""
    if image_exists(image):
        return True, f"image ready ({image_digest(image)[:12]})"
    if not autobuild:
        return False, f"image {image} missing and autobuild is disabled"
    if not packages and not r_packages:
        ok, log = pull_image(image)
        if ok:
            return True, f"image pulled ({image_digest(image)[:12]})"
        return False, f"image pull failed: {log}"
    ok, log = build_image(
        image, base=base, packages=packages, context_dir=context_dir, r_packages=r_packages
    )
    if ok:
        return True, f"image built ({image_digest(image)[:12]})"
    return False, f"image build failed: {log}"
