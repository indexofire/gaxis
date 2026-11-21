"""Naming helpers for KB template assets (importable without the service layer)."""

from __future__ import annotations

SCRIPT_NAMES = {"python": "figure.py", "r": "figure.R"}


def template_slug(preset: str, chart: str, backend: str) -> str:
    return f"template:{preset}-{chart}-{backend}"


def template_code_relpath(preset: str, chart: str, backend: str) -> str:
    return f"assets/templates/{preset}/{chart}-{backend}/{SCRIPT_NAMES[backend]}"
