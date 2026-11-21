"""Data provenance: profiling a user-supplied tidy table into a ``DataSchema``."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

MISSING_TOKENS = frozenset({"", "na", "n/a", "nan", "null", "none", "."})
_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?([T ]\d{2}:\d{2}(:\d{2})?)?$")
_UNIT_RE = re.compile(r"[\(\[]([^\)\]]+)[\)\]]")
_UNITS = {
    "fpkm": "FPKM",
    "tpm": "TPM",
    "rpm": "RPM",
    "cpm": "CPM",
    "kg": "kg",
    "mg": "mg",
    "mm": "mm",
    "cm": "cm",
    "nm": "nm",
    "ml": "mL",
    "ul": "uL",
    "h": "h",
    "min": "min",
    "sec": "s",
    "pct": "%",
    "percent": "%",
}
_DELIMITERS = {".tsv": "\t", ".tab": "\t", ".psv": "|"}


class ColumnKind(StrEnum):
    numeric = "numeric"
    categorical = "categorical"
    datetime = "datetime"
    boolean = "boolean"
    unknown = "unknown"


class ColumnProfile(BaseModel):
    """Everything the spec inference and the LLM need to know about one column."""

    name: str
    kind: ColumnKind
    n_unique: int
    missing_ratio: float = 0.0
    sample_values: list[str] = Field(default_factory=list)
    unit_hint: str | None = None

    def as_line(self) -> str:
        unit = f" [{self.unit_hint}]" if self.unit_hint else ""
        samples = ", ".join(self.sample_values[:3])
        return (
            f"- `{self.name}`: {self.kind}{unit}, "
            f"{self.n_unique} unique, {self.missing_ratio:.0%} missing, e.g. {samples}"
        )


class DataSchema(BaseModel):
    """Profiled table. ``sha256`` binds every artifact back to the exact input."""

    path: str
    format: str
    delimiter: str = ","
    n_rows: int
    columns: list[ColumnProfile]
    sha256: str

    def column(self, name: str) -> ColumnProfile | None:
        return next((c for c in self.columns if c.name == name), None)

    def has(self, name: str) -> bool:
        return self.column(name) is not None

    def of_kind(self, *kinds: ColumnKind) -> list[ColumnProfile]:
        return [c for c in self.columns if c.kind in kinds]

    @property
    def numeric_columns(self) -> list[str]:
        return [c.name for c in self.of_kind(ColumnKind.numeric)]

    @property
    def categorical_columns(self) -> list[str]:
        return [c.name for c in self.of_kind(ColumnKind.categorical, ColumnKind.boolean)]

    def n_unique(self, name: str) -> int:
        profile = self.column(name)
        return profile.n_unique if profile else 0

    def summary_markdown(self) -> str:
        head = f"{self.n_rows} rows x {len(self.columns)} columns ({Path(self.path).name})"
        return "\n".join([head, *(c.as_line() for c in self.columns)])


def _is_missing(value: str) -> bool:
    return value.strip().lower() in MISSING_TOKENS


def _as_float(value: str) -> float | None:
    try:
        return float(value.strip().replace("_", ""))
    except ValueError:
        return None


def _unit_hint(name: str) -> str | None:
    bracketed = _UNIT_RE.search(name)
    if bracketed:
        return bracketed.group(1).strip()
    for token in reversed(re.split(r"[_\-\s]+", name.lower())):
        if token in _UNITS:
            return _UNITS[token]
    return None


def guess_delimiter(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    if suffix in _DELIMITERS:
        return _DELIMITERS[suffix]
    header = text.splitlines()[0] if text.splitlines() else ""
    counts = {d: header.count(d) for d in (",", "\t", ";", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] else ","


def _infer_kind(raw: Iterable[str], n_rows: int) -> ColumnKind:
    present = [v for v in raw if not _is_missing(v)]
    if not present:
        return ColumnKind.unknown
    lowered = {v.strip().lower() for v in present}
    if lowered and lowered <= {"true", "false", "yes", "no"} and len(present) == n_rows:
        return ColumnKind.boolean
    if all(_as_float(v) is not None for v in present):
        return ColumnKind.numeric
    if all(_DATE_RE.match(v.strip()) for v in present):
        return ColumnKind.datetime
    return ColumnKind.categorical


def describe_data(path: str | Path) -> DataSchema:
    """Read a CSV/TSV file and profile every column."""
    file = Path(path).expanduser()
    if not file.is_file():
        raise FileNotFoundError(f"data file not found: {file}")
    text = file.read_text(encoding="utf-8-sig")
    delimiter = guess_delimiter(file, text)
    rows = _read_rows(text, delimiter)
    if not rows:
        raise ValueError(f"data file has no rows: {file}")
    header, body = rows[0], rows[1:]
    columns: list[ColumnProfile] = []
    for index, name in enumerate(header):
        raw = [row[index] if index < len(row) else "" for row in body]
        missing = sum(1 for v in raw if _is_missing(v))
        samples = [v.strip() for v in raw if not _is_missing(v)][:3]
        columns.append(
            ColumnProfile(
                name=name.strip(),
                kind=_infer_kind(raw, len(body)),
                n_unique=len({v.strip() for v in raw if not _is_missing(v)}),
                missing_ratio=round(missing / len(raw), 4) if raw else 0.0,
                sample_values=samples,
                unit_hint=_unit_hint(name),
            )
        )
    return DataSchema(
        path=str(file.resolve()),
        format=file.suffix.lower().lstrip(".") or "csv",
        delimiter=delimiter,
        n_rows=len(body),
        columns=columns,
        sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
    )


def _read_rows(text: str, delimiter: str) -> list[list[str]]:
    import csv
    import io

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [row for row in reader if any(cell.strip() for cell in row)]
