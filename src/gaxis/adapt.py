"""Adapt a retrieved template script to local data, without re-emitting it.

The knowledge base stores scripts, not specs. Adaptation therefore rewrites the
module-level constants a human would edit (data path, output dir, stem, delimiter,
encoding intent) and leaves the plotting code — the part worth reusing — untouched.
Every rewrite is verified; a template whose shape is unexpected is refused instead of
silently running the wrong thing.
"""

from __future__ import annotations

import pprint
from pathlib import Path

from .errors import GaxisError
from .models.spec import ChartSpec

PY_HEADERS = ("DATA_PATH = Path(", "OUT_DIR = Path(", "STEM = ", "DELIMITER = ", "SPEC = {")
R_HEADERS = ("DATA_PATH <- ", "OUT_DIR <- ", "STEM <- ", "SEP <- ", "SPEC <- list(")


def delimiter_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".tsv", ".tab"}:
        return "\t"
    if suffix == ".csv":
        return ","
    return ","


def _py_spec_payload(spec: ChartSpec) -> dict[str, object]:
    return {
        "chart_type": spec.chart_type.value,
        "x": spec.x,
        "y": spec.y,
        "hue": spec.hue,
        "yerr": spec.yerr,
        "weight": spec.weight,
        "annotations": list(spec.annotations),
        "title": spec.title,
        "xlabel": spec.xlabel,
        "ylabel": spec.ylabel,
        "annotate": spec.annotate_values,
        "formats": list(spec.formats),
    }


def _r_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "c(" + ", ".join(_r_literal(item) for item in value) + ")"
    text = (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\t", "\\t")
        .replace("\n", "\\n")
    )
    return f'"{text}"'


def _r_spec_payload(spec: ChartSpec) -> dict[str, object]:
    return {
        "x": spec.x,
        "y": spec.y,
        "hue": spec.hue,
        "yerr": spec.yerr,
        "weight": spec.weight,
        "annotations": list(spec.annotations),
        "title": spec.title,
        "xlabel": spec.xlabel,
        "ylabel": spec.ylabel,
        "annotate": spec.annotate_values,
        "formats": list(spec.formats),
    }


def _replace_block(
    lines: list[str],
    header: str,
    replacement: list[str],
    *,
    close: str | None = None,
    exact_close: bool = False,
) -> bool:
    """Replace the assignment that starts at ``header`` (through ``close`` if given)."""
    for index, line in enumerate(lines):
        if not line.startswith(header):
            continue

        def is_close(candidate: str) -> bool:
            stripped = candidate.strip()
            return stripped == close if exact_close else stripped.endswith(close or "")

        end = index + 1
        if close is not None and not is_close(lines[index]):
            while end < len(lines) and not is_close(lines[end]):
                end += 1
            if end == len(lines):
                return False
            end += 1
        lines[index:end] = replacement
        return True
    return False


def adapt_script(
    template: str,
    *,
    backend: str,
    spec: ChartSpec,
    data_path: Path,
    out_dir: Path,
    stem: str,
    delimiter: str,
) -> tuple[str, list[str]]:
    """Return (adapted source, list of applied rewrites) or raise ``adaptation_failed``."""
    lines = template.splitlines()
    applied: list[str] = []
    if backend == "python":
        rewrites = [
            ("DATA_PATH = Path(", [f"DATA_PATH = Path({str(data_path)!r})"], "data path"),
            ("OUT_DIR = Path(", [f"OUT_DIR = Path({str(out_dir)!r})"], "output dir"),
            ("STEM = ", [f"STEM = {stem!r}"], "stem"),
            ("DELIMITER = ", [f"DELIMITER = {delimiter!r}"], "delimiter"),
        ]
        spec_lines = ["SPEC = " + pprint.pformat(_py_spec_payload(spec), width=88, sort_dicts=True)]
        rewrites.append(("SPEC = {", spec_lines, "encoding intent"))
        close = "}"
    elif backend == "r":
        rewrites = [
            ("DATA_PATH <- ", [f"DATA_PATH <- {_r_literal(str(data_path))}"], "data path"),
            ("OUT_DIR <- ", [f"OUT_DIR <- {_r_literal(str(out_dir))}"], "output dir"),
            ("STEM <- ", [f"STEM <- {_r_literal(stem)}"], "stem"),
            ("SEP <- ", [f"SEP <- {_r_literal(delimiter)}"], "delimiter"),
        ]
        payload = _r_spec_payload(spec)
        entries = [f"  {key} = {_r_literal(value)}" for key, value in payload.items()]
        spec_lines = ["SPEC <- list(", ",\n".join(entries), ")"]
        rewrites.append(("SPEC <- list(", spec_lines, "encoding intent"))
        close = ")"
    else:
        raise GaxisError("unsupported_backend", f"cannot adapt backend {backend!r}")

    for header, replacement, label in rewrites:
        block_close = close if header.startswith("SPEC") else None
        if not _replace_block(
            lines,
            header,
            replacement,
            close=block_close,
            exact_close=backend == "r",
        ):
            raise GaxisError(
                "adaptation_failed",
                f"template is missing the {label} assignment ({header.strip()!r})",
                hint=(
                    "the asset was not emitted by a gaxis template; rebuild it with `gaxis kb seed`"
                ),
            )
        applied.append(label)
    return "\n".join(lines) + "\n", applied
