"""Lint model — the machine-readable form of "publication grade"."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    error = "error"
    warning = "warning"
    info = "info"


class LintIssue(BaseModel):
    code: str
    severity: Severity
    message: str
    subject: str | None = None


class LintReport(BaseModel):
    issues: list[LintIssue] = Field(default_factory=list)

    @property
    def errors(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity is Severity.error]

    @property
    def warnings(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity is Severity.warning]

    @property
    def ok(self) -> bool:
        return not self.errors

    def format_text(self) -> str:
        if not self.issues:
            return "lint: clean"
        symbol = {Severity.error: "E", Severity.warning: "W", Severity.info: "I"}
        return "\n".join(
            f"{symbol[i.severity]} {i.code} {i.message}"
            for i in sorted(self.issues, key=lambda i: list(symbol).index(i.severity))
        )
