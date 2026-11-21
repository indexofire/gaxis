"""LLM-assisted figure reconstruction: the model writes code, the sandbox judges it.

This is the fallback for figures whose author code is missing or does not run. It never
claims to be an author reproduction: every manifest records ``reproduction.method`` and
``model``, and the code candidate carries ``generated: true``. The loop is always the same:
generate a script -> run it in the sandbox -> compare with the reference image -> feed the
rendered image, the similarity components and any traceback back to the model.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import GaxisConfig
from ..design_judge import _prepare_image
from ..errors import GaxisError
from ..models.manifest import OutputFile
from ..models.paper import ChartReproManifest, CodeCandidate
from ..models.reconstruct import ReconstructResult
from ..sandbox.base import Mount, Sandbox, SandboxSpec
from ..sandbox.image import ensure_image
from ..sandbox.local import LocalSandbox
from ..sandbox.podman import PodmanSandbox, podman_available
from ..sandbox.scan import scan_code
from .compare import compare_images, raster_candidates
from .grade import grade_reproduction

SYSTEM_PROMPT = """\
You write a standalone Python script that reproduces a published scientific figure from a
reference image. The script is executed in an offline sandbox.

Hard rules:
- Only the Python standard library, matplotlib and numpy. No pandas, no network, no
  subprocess, no reading files other than the optional input table.
- If the environment variable GAXIS_DATA is set, read that file with the csv module. Choose
  the delimiter from the file extension (.tsv/.tab -> tab, otherwise comma); do NOT use
  csv.Sniffer. Otherwise use the data values you infer from the image.
- Use matplotlib with matplotlib.use("Agg"), white background, and a figure size that
  matches the reference aspect ratio.
- Save the result as "reconstruction.png" (dpi=600) and "reconstruction.pdf".
- Match the reference as closely as possible: chart type, axis labels and units, ticks,
  legend placement, colours, font sizes, error bars, panel letters.
- Keep the script deterministic (no random values unless the image requires noise).
Return ONLY one ```python fenced code block, no prose.
"""

REVISE_PROMPT = """\
The rendered figure is below, next to the reference. Similarity components (0-1):
{components}
Run output:
{error}

Fix the script so the rendered figure gets closer to the reference. Typical causes: wrong
chart type, missing/incorrect labels and units, wrong axis limits or ticks, legend in the
wrong place, wrong colours, wrong figure size or margins, missing error bars.
The script must parse as valid Python: never put a literal line break inside a string
literal (write "\\n" for a newline escape).
Return the complete corrected script in one ```python fenced code block.
"""


@dataclass
class Attempt:
    round: int
    code: str
    run_ok: bool
    similarity: float | None
    detail: dict[str, float] = field(default_factory=dict)
    error: str = ""
    outputs: list[Path] = field(default_factory=list)
    render: Path | None = None
    image_id: str = ""
    engine: str = "local"


@dataclass
class ReconstructOutcome:
    result: ReconstructResult
    manifest: ChartReproManifest
    manifest_path: Path


def _endpoint(
    config: GaxisConfig, model_override: str | None = None
) -> tuple[str, str, str, int, float, float, int, bool]:
    recon = config.reconstruct
    design = config.design
    base_url = (recon.base_url or design.base_url).rstrip("/")
    model = model_override or recon.model or design.model
    api_key_env = recon.api_key_env or design.api_key_env
    return (
        base_url,
        model,
        api_key_env,
        recon.max_side,
        recon.timeout_s,
        recon.temperature,
        recon.max_tokens,
        recon.disable_thinking,
    )


def _encode(path: Path, max_side: int) -> str:
    return base64.b64encode(_prepare_image(path.read_bytes(), max_side)).decode()


def _request_code(
    *,
    base_url: str,
    model: str,
    api_key: str,
    max_side: int,
    timeout_s: float,
    temperature: float,
    max_tokens: int,
    disable_thinking: bool,
    reference: Path,
    caption: str,
    hints: str,
    previous_code: str = "",
    rendered: Path | None = None,
    feedback: str = "",
) -> str:
    parts: list[dict[str, Any]] = [
        {"type": "text", "text": SYSTEM_PROMPT},
        {"type": "text", "text": "Reference figure:"},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{_encode(reference, max_side)}"},
        },
        {"type": "text", "text": f"Caption:\n{caption or '(no caption)'}\n\nHints:\n{hints}"},
    ]
    if previous_code:
        parts.append(
            {"type": "text", "text": "Previous script:\n```python\n" + previous_code + "\n```"}
        )
    if rendered is not None:
        parts.append({"type": "text", "text": "Rendered result:"})
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{_encode(rendered, max_side)}"},
            }
        )
    if feedback:
        parts.append({"type": "text", "text": feedback})
    payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": parts}],
    }
    if disable_thinking and model.startswith("glm-5"):
        payload["thinking"] = {"type": "disabled"}
    request = urllib.request.Request(  # noqa: S310 - configured endpoint
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
                body = json.load(response)
            content = body["choices"][0]["message"]["content"]
            return _extract_code(content)
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            ValueError,
            KeyError,
        ) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise GaxisError("reconstruct_failed", f"model request failed: {last_error}")


def _unclosed_quote(line: str) -> bool:
    """True when a physical line ends inside a single/double-quoted string."""
    if chr(34) * 3 in line or chr(39) * 3 in line:
        return False
    single = double = False
    escaped = False
    for char in line:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == chr(39) and not double:
            single = not single
        elif char == chr(34) and not single:
            double = not double
        elif char == "#" and not single and not double:
            break
    return single or double


def _join_multiline_strings(code: str, *, max_lines: int = 3) -> str:
    """Join raw newlines inside one-line string literals (a common model mistake)."""
    lines = code.splitlines()
    merged: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        joins = 0
        while _unclosed_quote(line) and index + 1 < len(lines) and joins < max_lines:
            index += 1
            joins += 1
            line = line + "\\n" + lines[index].strip()
        merged.append(line)
        index += 1
    return "\n".join(merged)


def _normalise_code(code: str) -> str:
    """Deterministic fixes for mistakes that are pure syntax, not design decisions."""
    import ast

    base = code.strip()
    if "plt.use(" in base and "matplotlib.use(" not in base:
        base = base.replace("plt.use(", "matplotlib.use(")
    import re

    has_matplotlib = re.search(r"^import matplotlib(\s|$)", base, re.MULTILINE)
    if has_matplotlib is None and "matplotlib." in base:
        base = "import matplotlib\n" + base
    try:
        ast.parse(base)
    except SyntaxError:
        joined = _join_multiline_strings(base)
        try:
            ast.parse(joined)
        except SyntaxError:
            return base + "\n"
        base = joined
    return base + "\n"


def _extract_code(content: str) -> str:
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", content, re.S)
    code = match.group(1).strip() if match else content.strip()
    if "savefig" not in code:
        raise GaxisError("reconstruct_failed", "model returned no script with savefig")
    return _normalise_code(code)


def _pick_sandbox(config: GaxisConfig, engine: str | None) -> tuple[Sandbox, str, str]:
    sandbox_cfg = config.sandbox
    chosen = engine or sandbox_cfg.backend
    if chosen == "podman":
        if not podman_available():
            return LocalSandbox(), "", "podman unavailable: local engine (no isolation)"
        ready, message = ensure_image(
            sandbox_cfg.image,
            autobuild=sandbox_cfg.autobuild,
            packages=sandbox_cfg.autobuild_packages,
            context_dir=Path("data") / "sandbox",
            base="docker.io/library/python:3.12-slim",
        )
        if ready:
            return PodmanSandbox(), sandbox_cfg.image, message
        return LocalSandbox(), "", f"image not ready ({message}); local engine (no isolation)"
    return LocalSandbox(), "", "local engine requested (no isolation)"


def _slug(manifest_id: str) -> str:
    return manifest_id.replace("/", "__").replace(" ", "_")


def _run_once(
    code: str,
    *,
    workdir: Path,
    reference: Path,
    data_path: Path | None,
    config: GaxisConfig,
    engine: str | None,
    timeout_s: float,
) -> Attempt:
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / "figure.py"
    script.write_text(code, encoding="utf-8")
    import ast

    try:
        ast.parse(code)
    except SyntaxError as exc:
        return Attempt(0, code, False, None, error=f"SyntaxError: {exc.msg} (line {exc.lineno})")
    report = scan_code(script)
    if report.blocking:
        codes = sorted(
            {finding.code for finding in report.findings if finding.severity == "critical"}
        )
        return Attempt(0, code, False, None, error=f"static scan blocked: {', '.join(codes)}")

    sandbox, image, _note = _pick_sandbox(config, engine)
    mounts: list[Mount] = []
    env: dict[str, str] = {}
    if data_path is not None:
        mounts.append(Mount(source=data_path.parent, target="/data", read_only=True))
        env["GAXIS_DATA"] = f"/data/{data_path.name}"
    if sandbox.engine == "local" and data_path is not None:
        env["GAXIS_DATA"] = str(data_path)
    spec = SandboxSpec(
        script=script,
        workdir=workdir,
        mounts=tuple(mounts),
        timeout_s=timeout_s,
        network=False,
        image=image or config.sandbox.image,
        memory=config.sandbox.memory,
        cpus=config.sandbox.cpus,
        pids_limit=config.sandbox.pids_limit,
        env=env,
    )
    started = time.time()
    run = sandbox.run(spec)
    produced = raster_candidates(
        [path for path in run.outputs if path.is_file()] if run.outputs else []
    )
    if not produced:
        produced = raster_candidates(
            [
                path
                for path in workdir.rglob("*")
                if path.is_file() and path.stat().st_mtime >= started - 2
            ]
        )
    similarity = None
    detail: dict[str, float] = {}
    render: Path | None = None
    if produced:
        render = max(produced, key=lambda path: path.stat().st_size)
        comparison = compare_images(reference, render, size=config.reproduction.compare_size)
        similarity = comparison.score
        detail = comparison.as_dict()
    return Attempt(
        0,
        code,
        run.ok,
        similarity,
        detail,
        error="" if run.ok else run.tail(8),
        outputs=produced,
        render=render,
        image_id=str(run.report.get("image_id") or ""),
        engine=sandbox.engine,
    )


def reconstruct_manifest(
    manifest: ChartReproManifest,
    *,
    manifest_path: Path,
    reference: Path,
    data_path: Path | None,
    engine: str | None,
    rounds: int,
    target: float,
    data_root: Path,
    config: GaxisConfig,
    repair_code: str = "",
    model_override: str | None = None,
    timeout_override: float | None = None,
    max_side_override: int | None = None,
) -> ReconstructOutcome:
    if not reference.is_file():
        raise GaxisError("reference_missing", f"reference figure not found: {reference}")
    if reference.suffix.lower() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        raise GaxisError(
            "reference_unsupported",
            f"reference must be a raster image, got {reference.suffix}",
            hint="render the paper figure to PNG first",
        )
    (
        base_url,
        model,
        key_env,
        max_side,
        timeout_s,
        temperature,
        max_tokens,
        disable_thinking,
    ) = _endpoint(config, model_override)
    api_key = os.environ.get(key_env, "")
    local = any(host in base_url for host in ("127.0.0.1", "localhost"))
    if not api_key and not local:
        raise GaxisError(
            "reconstruct_unconfigured",
            f"no API key in {key_env}",
            hint="set [reconstruct] base_url/model/api_key_env (or [design]) and export the key",
        )
    chart = manifest.visual_grammar.chart_type.value if manifest.visual_grammar.chart_type else ""
    hints = "\n".join(
        item
        for item in (
            f"Chart type: {chart}" if chart else "",
            f"Figure reference: {manifest.figure_ref}",
            "Visual grammar notes: " + "; ".join(manifest.visual_grammar.notes)
            if manifest.visual_grammar.notes
            else "",
        )
        if item
    )
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{_slug(model)}"
    base_dir = data_root / "recon" / _slug(manifest.manifest_id) / run_id
    attempts: list[Attempt] = []
    code = repair_code
    for round_number in range(1, rounds + 1):
        if not code:
            code = _request_code(
                base_url=base_url,
                model=model,
                api_key=api_key,
                max_side=max_side,
                timeout_s=timeout_s,
                temperature=temperature,
                max_tokens=max_tokens,
                disable_thinking=disable_thinking,
                reference=reference,
                caption=manifest.caption,
                hints=hints,
            )
        attempt = _run_once(
            code,
            workdir=base_dir / f"round-{round_number}",
            reference=reference,
            data_path=data_path,
            config=config,
            engine=engine,
            timeout_s=timeout_s,
        )
        attempt.round = round_number
        attempts.append(attempt)
        (base_dir / f"round-{round_number}" / "attempt.json").write_text(
            json.dumps(
                {
                    "round": round_number,
                    "run_ok": attempt.run_ok,
                    "similarity": attempt.similarity,
                    "components": attempt.detail,
                    "engine": attempt.engine,
                    "image_id": attempt.image_id,
                    "error": attempt.error,
                    "outputs": [str(path) for path in attempt.outputs],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if attempt.similarity is not None and attempt.similarity >= target:
            break
        if round_number == rounds:
            break
        code = _request_code(
            base_url=base_url,
            model=model,
            api_key=api_key,
            max_side=max_side,
            timeout_s=timeout_s,
            temperature=temperature,
            max_tokens=max_tokens,
            disable_thinking=disable_thinking,
            reference=reference,
            caption=manifest.caption,
            hints=hints,
            previous_code=attempt.code,
            rendered=attempt.render,
            feedback=REVISE_PROMPT.format(
                components=json.dumps(attempt.detail, indent=2),
                error=attempt.error or "(none)",
            ),
        )
    best = max(
        attempts,
        key=lambda item: (item.similarity if item.similarity is not None else -1.0, item.run_ok),
    )
    grade = grade_reproduction(
        run_ok=best.run_ok,
        similarity=best.similarity,
        l1_threshold=config.reproduction.l1_similarity,
        l2_threshold=config.reproduction.l2_similarity,
        produces_raster=bool(best.render),
    )
    if not best.run_ok:
        # A generated script that does not even run is not a style template either.
        from .grade import Grade

        grade = Grade("none", f"generated script did not run after {len(attempts)} round(s)")
    code_sha = hashlib.sha256(best.code.encode()).hexdigest()
    if best.run_ok:
        asset = (
            data_root / "assets" / "code" / _slug(manifest.manifest_id) / f"recon-{code_sha[:8]}"
        )
        asset.mkdir(parents=True, exist_ok=True)
        asset_script = asset / "figure.py"
        asset_script.write_text(best.code, encoding="utf-8")
    else:
        asset_script = base_dir / f"round-{best.round}" / "figure.py"
    unchanged = bool(repair_code) and best.code.strip() == repair_code.strip()
    method = "author_code" if unchanged else ("llm_repair" if repair_code else "llm_reconstruction")
    manifest.reproduction.method = method  # type: ignore[assignment]
    manifest.reproduction.model = None if unchanged else f"{model}"
    manifest.reproduction.attempts = len(attempts)
    manifest.reproduction.level = grade.level
    manifest.reproduction.sandbox_run_status = (
        "success" if best.run_ok else ("skipped" if best.similarity is None else "failed")
    )
    manifest.reproduction.visual_similarity = best.similarity
    manifest.reproduction.failure_reason = grade.reason if grade.level != "L1" else ""
    manifest.reproduction.render_output = (
        str(best.render.relative_to(data_root))
        if best.render and best.render.is_relative_to(data_root)
        else None
    )
    manifest.reproduction.environment_lock = best.image_id or best.engine
    manifest.reproduction.data_source = "user" if data_path else "none"
    candidate = CodeCandidate(
        code_path=str(asset_script),
        language="python",
        entry_point="figure.py",
        packages=list(config.sandbox.autobuild_packages),
        license="generated",
        pairing_confidence=1.0,
        code_sha256=code_sha,
        generated=True,
    )
    if best.run_ok and not unchanged:
        manifest.code_candidates = [item for item in manifest.code_candidates if not item.generated]
        manifest.code_candidates.append(candidate)
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    outputs = [
        OutputFile(
            path=str(path),
            format=path.suffix.lstrip(".").lower(),
            bytes=path.stat().st_size,
        )
        for path in best.outputs
    ]
    (base_dir / "reconstruction.json").write_text(
        json.dumps(
            {
                "manifest_id": manifest.manifest_id,
                "method": method,
                "model": None if unchanged else model,
                "reference": str(reference),
                "target_similarity": target,
                "rounds": [
                    {
                        "round": item.round,
                        "run_ok": item.run_ok,
                        "similarity": item.similarity,
                        "components": item.detail,
                        "error": item.error,
                        "engine": item.engine,
                        "image_id": item.image_id,
                    }
                    for item in attempts
                ],
                "best_round": best.round,
                "level": grade.level,
                "reason": grade.reason,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = ReconstructResult(
        manifest_id=manifest.manifest_id,
        method=method,
        level=grade.level,
        visual_similarity=best.similarity,
        rounds=len(attempts),
        similarity_history=[a.similarity for a in attempts if a.similarity is not None],
        outputs=outputs,
        code_path=str(asset_script),
        code_sha256=code_sha,
        engine=best.engine,
        model=None if unchanged else model,
        failure_reason=manifest.reproduction.failure_reason,
        manifest_path=str(manifest_path),
    )
    return ReconstructOutcome(result=result, manifest=manifest, manifest_path=manifest_path)
