"""Synthetic input data for scripts whose real data is unavailable.

This is an explicit, labelled degradation, never a silent one: columns are inferred from
how the script reads its table, plausible values are generated, and the reproduction
records ``data_source: "synthetic"``. A figure built on synthetic data can show that the
code runs and the structure matches; it cannot claim the paper's numbers.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

NUMERIC_HINTS = (
    "value",
    "count",
    "freq",
    "abundance",
    "expression",
    "expr",
    "od",
    "time",
    "depth",
    "score",
    "rate",
    "ratio",
    "length",
    "size",
    "log",
    "n_",
    "num",
    "mean",
    "sd",
    "se",
    "fpkm",
    "tpm",
    "reads",
)
CATEGORICAL_HINTS = ("group", "condition", "genotype", "strain", "sample", "treatment", "taxon")


def infer_columns(code_path: Path) -> list[str]:
    """Column names the script indexes, in first-appearance order."""
    try:
        text = code_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    names: list[str] = []
    for match in re.finditer(r"\[\s*[\"']([A-Za-z_][\w .\-]*)[\"']\s*\]", text):
        name = match.group(1)
        if name not in names:
            names.append(name)
    if not names:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and re.fullmatch(r"[A-Za-z_][\w .\-]*", node.value)
                and len(node.value) > 1
                and node.value not in names
            ):
                names.append(node.value)
    return names[:12]


def _is_numeric(name: str) -> bool:
    lowered = name.lower()
    if any(hint in lowered for hint in CATEGORICAL_HINTS):
        return False
    return any(lowered == hint or hint in lowered for hint in NUMERIC_HINTS)


def generate_csv(columns: list[str], out_path: Path, *, rows: int = 12, seed: str = "") -> Path:
    """Write a tidy table with plausible values; deterministic for a given seed."""
    if not columns:
        columns = ["group", "value"]
    digest = hashlib.sha256((seed or "|".join(columns)).encode()).hexdigest()
    offset = int(digest[:6], 16) % 17
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(columns)]
    groups = ["A", "B", "C", "D"]
    for index in range(rows):
        values: list[str] = []
        for position, column in enumerate(columns):
            if _is_numeric(column):
                base = 5 + (position * 3) + offset
                value = base + (index % 6) * 1.37 + (index % 3) * 0.42
                values.append(f"{value:.2f}")
            else:
                values.append(groups[(index + position) % len(groups)])
        lines.append(",".join(values))
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
