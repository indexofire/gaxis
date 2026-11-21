"""Static scan + licence check before anything executes (module D in the plan).

The scan is deliberately conservative and advisory-first: it reports findings with
severity, and only *blocking* findings stop a run. A blocked run is a documented
outcome, not an exception the host has to guess about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CRITICAL_RULES: list[tuple[str, str, str]] = [
    ("shell_exec", r"\bos\.system\s*\(", "shell command execution"),
    ("subprocess", r"\bsubprocess\.(run|Popen|call|check_output)\s*\(", "spawns processes"),
    ("eval_exec", r"\b(eval|exec)\s*\(", "dynamic code execution"),
    ("ctypes", r"\bctypes\b", "native memory access"),
    ("ssh_paths", r"(\.ssh|id_rsa|/etc/shadow|/etc/passwd)", "credential/host paths"),
    (
        "destructive_fs",
        r"\bshutil\.rmtree\s*\(|os\.remove\s*\(\s*['\"]/",
        "destructive filesystem calls",
    ),
]

WARNING_RULES: list[tuple[str, str, str]] = [
    ("network", r"\b(requests|urllib|httpx|socket|aiohttp)\.", "network access"),
    ("absolute_write", r"open\s*\(\s*['\"]/(?!tmp|work)", "writes outside the work dir"),
    ("pickle", r"\bpickle\.loads?\b|\bjoblib\.load\b", "untrusted deserialisation"),
]

_LICENCE_PATTERNS = [
    (
        "GPL",
        re.compile(r"\b(GPL|GNU General Public License|General Public License)\b", re.IGNORECASE),
    ),
    ("AGPL", re.compile(r"\bAGPL\b", re.IGNORECASE)),
    ("LGPL", re.compile(r"\bLGPL\b", re.IGNORECASE)),
]


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # critical | warning | info
    message: str
    line: int


@dataclass(frozen=True)
class ScanReport:
    findings: tuple[Finding, ...] = ()
    licences: tuple[str, ...] = ()

    @property
    def blocking(self) -> bool:
        return any(finding.severity == "critical" for finding in self.findings)

    @property
    def copyleft(self) -> bool:
        return any(name in {"GPL", "AGPL"} for name in self.licences)

    def as_dict(self) -> dict[str, object]:
        return {
            "findings": [
                {"code": f.code, "severity": f.severity, "message": f.message, "line": f.line}
                for f in self.findings
            ],
            "licences": list(self.licences),
            "blocking": self.blocking,
            "copyleft": self.copyleft,
        }


def scan_code(path: Path) -> ScanReport:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for code, pattern, message in CRITICAL_RULES:
            if re.search(pattern, line):
                findings.append(Finding(code, "critical", message, number))
        for code, pattern, message in WARNING_RULES:
            if re.search(pattern, line):
                findings.append(Finding(code, "warning", message, number))
    licences = tuple(name for name, pattern in _LICENCE_PATTERNS if pattern.search(text))
    return ScanReport(findings=tuple(findings), licences=licences)


def dependency_hints(path: Path, *, stdlib: frozenset[str] | None = None) -> list[str]:
    """Top-level imports, used to decide what an environment needs (plan C2)."""
    import ast
    import sys

    known = stdlib if stdlib is not None else frozenset(sys.stdlib_module_names)
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    modules: set[str] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return sorted({name for name in modules if name and name not in known and name != "gaxis"})
