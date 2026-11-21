"""Promote a reproduced paper script to an adaptable template.

Arbitrary research code cannot be rebased onto a new table automatically, so adoption is
an explicit act with a small, checkable contract: the script must bind its input through
``DATA_PATH`` (Python assignment or R ``<-``). When it does, the template records that
interface and `adapt_chart_code` may rebind the path and run it; when it does not, adoption
refuses with a reason instead of guessing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ..errors import GaxisError
from ..models.paper import ChartReproManifest
from .base import KnowledgeBase
from .names import SCRIPT_NAMES
from .pages import _yaml_value

PY_PATTERN = re.compile(r"^DATA_PATH\s*=\s*.*$", re.MULTILINE)
R_PATTERN = re.compile(r"^DATA_PATH\s*<-\s*.*$", re.MULTILINE)
OUT_PY = re.compile(r"^OUT_DIR\s*=\s*.*$", re.MULTILINE)
OUT_R = re.compile(r"^OUT_DIR\s*<-\s*.*$", re.MULTILINE)


@dataclass
class AdoptedTemplate:
    slug: str
    code_path: str
    code_sha256: str
    backend: str
    chart_type: str
    source_asset: str
    interface: str


def _backend_of(path: Path) -> str:
    return "python" if path.suffix == ".py" else "r"


def detect_interface(code: str, backend: str) -> str:
    """Return ``"path"`` when the script documents a rebindable input, else raise."""
    pattern = PY_PATTERN if backend == "python" else R_PATTERN
    if not pattern.search(code):
        raise GaxisError(
            "adoption_refused",
            "the script does not bind its input through DATA_PATH",
            hint="expose the input file as DATA_PATH (and optionally OUT_DIR) and adopt again",
        )
    return "path"


def adopt_asset(
    kb: KnowledgeBase,
    *,
    manifest: ChartReproManifest,
    data_root: Path,
    code: Path | None = None,
    preset: str = "default",
) -> AdoptedTemplate:
    candidate = code or (
        Path(manifest.code_candidates[-1].code_path) if manifest.code_candidates else None
    )
    if candidate is None or not candidate.is_file():
        raise GaxisError(
            "code_required",
            f"{manifest.manifest_id} has no local script to adopt",
            hint="run reproduce_chart_code first, or pass --code path/to/script",
        )
    backend = _backend_of(candidate)
    text = candidate.read_text(encoding="utf-8")
    interface = detect_interface(text, backend)
    relative = (
        f"assets/templates/paper/{manifest.manifest_id.replace('/', '-')}/{SCRIPT_NAMES[backend]}"
    )
    stable = data_root / relative
    stable.parent.mkdir(parents=True, exist_ok=True)
    stable.write_text(text, encoding="utf-8")
    code_sha = hashlib.sha256(text.encode()).hexdigest()
    slug = f"template:paper-{manifest.manifest_id.replace('/', '-')}"
    chart_type = (
        manifest.visual_grammar.chart_type.value
        if manifest.visual_grammar.chart_type
        else "unknown"
    )
    license_name = next((item.license for item in manifest.code_candidates if item.license), None)
    front = {
        "type": "template",
        "title": f"{manifest.figure_ref} — {backend} (adopted paper script)",
        "chart_type": chart_type,
        "backend": backend,
        "preset": preset,
        "origin": "paper",
        "source_asset": manifest.manifest_id,
        "interface": interface,
        "reproduction_level": manifest.reproduction.level or "none",
        "code_path": relative,
        "code_sha256": code_sha,
        "license": license_name,
        "paper_title": manifest.paper_title,
        "doi": manifest.doi,
        "tags": "template,paper,adopted",
    }
    lines = ["---"]
    for key, value in front.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.extend(["---", "", f"# {manifest.figure_ref} — adopted paper script", ""])
    lines.append(
        "Adopted from a reproduced paper figure. The script reads its input from "
        "`DATA_PATH`; adaptation rebinds only that constant and runs the script unchanged. "
        "Column names are the paper's — map your table before adapting."
    )
    lines.extend(["", "## Script", "", "```" + ("python" if backend == "python" else "r")])
    lines.append(text.rstrip())
    lines.append("```")
    lines.append("")
    kb.put_page(slug, "\n".join(lines), reason=f"adopt {manifest.manifest_id}")
    return AdoptedTemplate(
        slug=slug,
        code_path=str(stable),
        code_sha256=code_sha,
        backend=backend,
        chart_type=chart_type,
        source_asset=manifest.manifest_id,
        interface=interface,
    )


def rewrite_path_interface(
    code: str, *, backend: str, data_path: Path, out_dir: Path | None = None
) -> str:
    """Rebind DATA_PATH (and OUT_DIR when present) without touching plotting code."""
    if backend == "python":
        pattern = PY_PATTERN
        out_pattern = OUT_PY
        data_line = f"DATA_PATH = Path({str(data_path)!r})"
        out_line = f"OUT_DIR = Path({str(out_dir)!r})" if out_dir else ""
    else:
        pattern = R_PATTERN
        out_pattern = OUT_R
        data_line = f"DATA_PATH <- {str(data_path).replace(chr(92), '/')!r}"
        out_line = f"OUT_DIR <- {str(out_dir).replace(chr(92), '/')!r}" if out_dir else ""
    updated, count = pattern.subn(data_line, code, count=1)
    if count != 1:
        raise GaxisError("adaptation_failed", "DATA_PATH assignment disappeared during rewrite")
    if out_dir is not None and out_pattern.search(updated):
        updated = out_pattern.sub(out_line, updated, count=1)
    return updated
