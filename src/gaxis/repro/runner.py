"""Reproduction orchestration (M2): scan -> sandbox -> compare -> grade -> persist.

Every step leaves evidence: the static-scan findings, the sandbox report (engine,
image id, limits, network), the similarity components, and the final level with its
reason. A host can therefore explain a grade instead of trusting it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config import GaxisConfig
from ..errors import GaxisError
from ..models.manifest import OutputFile
from ..models.paper import ChartReproManifest, CodeCandidate
from ..models.tools import ReproduceChartCodeResult
from ..sandbox.base import Mount, SandboxResult, SandboxSpec
from ..sandbox.image import ensure_image
from ..sandbox.local import LocalSandbox
from ..sandbox.podman import PodmanSandbox, podman_available
from ..sandbox.scan import dependency_hints, scan_code
from .compare import compare_images, raster_candidates
from .grade import grade_reproduction


@dataclass
class ReproductionOutcome:
    result: ReproduceChartCodeResult
    manifest: ChartReproManifest
    manifest_path: Path


def _slug(manifest_id: str) -> str:
    return manifest_id.replace("/", "__").replace(" ", "_")


def _paper_packages(manifest: ChartReproManifest, code_path: Path, configured: object) -> list[str]:
    """Pinned packages the paper's repo declares, merged with the base figure stack."""
    base = list(getattr(configured, "autobuild_packages", []) or [])
    declared: list[str] = []
    candidate_sha = hashlib.sha256(code_path.read_bytes()).hexdigest()
    for candidate in manifest.code_candidates:
        same_path = Path(candidate.code_path).resolve() == code_path
        same_sha = candidate.code_sha256 and candidate.code_sha256 == candidate_sha
        if same_path or same_sha:
            declared = list(candidate.packages)
            break
    merged = list(dict.fromkeys([*base, *declared]))
    return merged[:24]


def _packages_digest(packages: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(packages)).encode()).hexdigest()[:8]


def _pick_sandbox(engine: str):
    """The sandbox reads its image from the spec (python vs R images differ)."""
    if engine == "local":
        return LocalSandbox()
    if not podman_available():
        return None
    return PodmanSandbox()


def reproduce_manifest(
    manifest: ChartReproManifest,
    *,
    manifest_path: Path,
    code_path: Path,
    data_path: Path | None,
    engine: str | None,
    timeout_s: float | None,
    allow_network: bool,
    data_root: Path,
    config: GaxisConfig,
    data_source: str | None = None,
) -> ReproductionOutcome:
    code_path = Path(code_path).expanduser().resolve()
    if not code_path.is_file():
        raise GaxisError("code_not_found", f"code file not found: {code_path}")
    suffix = code_path.suffix.lower()
    language = "r" if suffix in {".r", ".rmd"} else "python"
    if suffix not in {".py", ".r", ".rmd", ""}:
        raise GaxisError(
            "unsupported_language",
            f"cannot run {suffix!r} scripts; supported: .py, .r",
            hint="convert the figure code to python or R",
        )
    code_bytes = code_path.read_bytes()
    code_sha = hashlib.sha256(code_bytes).hexdigest()
    scan = scan_code(code_path)
    dependencies = dependency_hints(code_path)

    workdir = data_root / "repro" / _slug(manifest.manifest_id) / code_sha[:8]
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / ("figure.R" if language == "r" else "figure.py")
    script.write_bytes(code_bytes)

    mounts: list[Mount] = []
    env: dict[str, str] = {}
    if data_path is not None:
        data_path = Path(data_path).expanduser().resolve()
        if not data_path.is_file():
            raise GaxisError("data_not_found", f"input data not found: {data_path}")
        mounts.append(Mount(source=data_path.parent, target="/data", read_only=True))
        env["GAXIS_DATA"] = f"/data/{data_path.name}"

    configured = config.sandbox
    chosen_engine = engine or configured.backend
    sandbox = _pick_sandbox(chosen_engine)
    notes: list[str] = []
    if sandbox is None:
        fallback = LocalSandbox()
        notes.append("podman unavailable: fell back to the local engine (no isolation)")
        sandbox = fallback
    packages: list[str] = []
    image = configured.r_image if language == "r" else configured.image
    if sandbox.engine == "podman":
        if language == "r":
            ready, message = ensure_image(
                image,
                autobuild=configured.autobuild,
                packages=None,
                context_dir=data_root / "sandbox",
                base=configured.r_base_image,
                r_packages=configured.r_packages,
            )
        else:
            packages = _paper_packages(manifest, code_path, configured)
            if packages and configured.per_paper_env:
                image = f"{configured.image.rsplit(':', 1)[0]}:pp-{_packages_digest(packages)}"
            ready, message = ensure_image(
                image,
                autobuild=configured.autobuild,
                packages=packages or configured.autobuild_packages,
                context_dir=data_root / "sandbox",
                base="docker.io/library/python:3.12-slim",
            )
            if not ready and image != configured.image:
                notes.append(f"per-paper image failed ({message}); using {configured.image}")
                image = configured.image
                ready, message = ensure_image(
                    image,
                    autobuild=configured.autobuild,
                    packages=configured.autobuild_packages,
                    context_dir=data_root / "sandbox",
                    base="docker.io/library/python:3.12-slim",
                )
        notes.append(message)
        if packages:
            notes.append(f"per-paper packages: {', '.join(packages)}")
        if not ready:
            notes.append("image not ready: falling back to the local engine")
            sandbox = LocalSandbox()
    if sandbox.engine == "local" and data_path is not None:
        # the local engine has no mount namespace: point it at the host path
        env["GAXIS_DATA"] = str(data_path)

    blocked_reason = ""
    if scan.blocking:
        critical = [finding.code for finding in scan.findings if finding.severity == "critical"]
        blocked_reason = f"static scan blocked the run ({', '.join(sorted(set(critical)))})"
    elif scan.copyleft:
        blocked_reason = (
            f"copyleft licence detected ({', '.join(scan.licences)}): reuse the logic, not the code"
        )

    run: SandboxResult | None = None
    similarity = None
    similarity_detail: dict[str, float] = {}
    render_output: Path | None = None
    produced: list[Path] = []
    if not blocked_reason:
        spec = SandboxSpec(
            script=script,
            workdir=workdir,
            mounts=tuple(mounts),
            timeout_s=timeout_s or configured.timeout_s,
            network=allow_network and configured.allow_network,
            image=image,
            memory=configured.memory,
            cpus=configured.cpus,
            pids_limit=configured.pids_limit,
            env=env,
            command=("Rscript", script.name) if language == "r" else (),
        )
        run = sandbox.run(spec)
        produced = raster_candidates(run.outputs)
        reference = data_root / manifest.chart_file if manifest.chart_file else None
        if produced and reference is not None and reference.is_file():
            best = max(produced, key=lambda path: path.stat().st_size)
            report = compare_images(reference, best, size=config.reproduction.compare_size)
            similarity = report.score
            similarity_detail = report.as_dict()
            render_output = best
        elif produced:
            render_output = max(produced, key=lambda path: path.stat().st_size)

    grade = grade_reproduction(
        run_ok=bool(run and run.ok),
        blocked_reason=blocked_reason,
        similarity=similarity,
        l1_threshold=config.reproduction.l1_similarity,
        l2_threshold=config.reproduction.l2_similarity,
        produces_raster=bool(produced),
    )
    failure_reason = grade.reason if grade.level != "L1" else ""
    if run is not None and not run.ok and not failure_reason:
        failure_reason = run.tail()
    if run is not None and not run.ok and grade.level == "L3":
        failure_reason = f"{grade.reason}: {run.tail(6)}"

    now = datetime.now(UTC)
    manifest.updated_at = now
    manifest.reproduction.level = grade.level
    manifest.reproduction.sandbox_run_status = (
        "success" if run and run.ok else ("skipped" if blocked_reason else "failed")
    )
    manifest.reproduction.visual_similarity = similarity
    manifest.reproduction.failure_reason = failure_reason
    manifest.reproduction.render_output = (
        str(render_output.relative_to(data_root)) if render_output else None
    )
    manifest.reproduction.environment_lock = (
        str((run.report.get("image_id") if run else None) or ("local" if run else "")) or None
    )
    source_kind = data_source or ("user" if data_path is not None else "none")
    if source_kind not in {"none", "user", "repo", "synthetic"}:
        source_kind = "user"
    manifest.reproduction.data_source = source_kind  # type: ignore[assignment]
    asset_path = (
        data_root
        / "assets"
        / "code"
        / _slug(manifest.manifest_id)
        / code_sha[:8]
        / ("figure.R" if language == "r" else "figure.py")
    )
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(code_path, asset_path)
    candidate = CodeCandidate(
        code_path=str(asset_path),
        language=language,  # type: ignore[arg-type]
        entry_point=script.name,
        dependency_hints=dependencies,
        packages=packages,
        license=scan.licences[0] if scan.licences else None,
        pairing_confidence=1.0,
        code_sha256=code_sha,
    )
    manifest.code_candidates = [
        existing
        for existing in manifest.code_candidates
        if Path(existing.code_path).resolve() not in {code_path, asset_path}
    ] + [candidate]
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    outputs = [
        OutputFile(
            path=str(path),
            format=path.suffix.lstrip(".").lower(),
            bytes=path.stat().st_size,
        )
        for path in produced
    ]
    sandbox_report = dict(run.report) if run else {}
    sandbox_report["scan"] = scan.as_dict()
    sandbox_report["notes"] = notes
    sandbox_report["dependencies"] = dependencies
    sandbox_report["packages"] = packages
    (workdir / "reproduction.json").write_text(
        json.dumps(
            {
                "manifest_id": manifest.manifest_id,
                "code_sha256": code_sha,
                "level": grade.level,
                "reason": grade.reason,
                "similarity": similarity_detail,
                "sandbox": sandbox_report,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    result = ReproduceChartCodeResult(
        manifest_id=manifest.manifest_id,
        level=grade.level,
        run_status=manifest.reproduction.sandbox_run_status,
        visual_similarity=similarity,
        failure_reason=failure_reason,
        outputs=outputs,
        engine=sandbox.engine,
        language=language,  # type: ignore[arg-type]
        code_path=str(code_path),
        code_sha256=code_sha,
        sandbox_report=sandbox_report,
        similarity_detail=similarity_detail,
        manifest_path=str(manifest_path),
        not_implemented=False,
    )
    if run is not None and run.stdout:
        sandbox_report["stdout_tail"] = run.stdout[-2000:]
    return ReproductionOutcome(result=result, manifest=manifest, manifest_path=manifest_path)
