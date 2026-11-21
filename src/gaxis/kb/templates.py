"""Seed the knowledge base with verified builtin templates.

A template asset is a real render: emitted script, PDF, lint report and manifest, all
produced by the same pipeline users get. Seeding is idempotent (page slug + code hash),
so it can run on any machine after a `pixi install` and gives `adapt_chart_code`
something verified to retrieve before any paper code exists.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..models.spec import ChartSpec, ChartType
from ..service import PIPELINE_VERSION, describe_data, render_spec
from ..style.presets import preset_names
from .base import KnowledgeBase, try_get_page
from .names import template_code_relpath, template_slug
from .pages import _yaml_value

# One canonical encoding per chart type; column names are synthetic and stable, so the
# emitted code reads like a real figure rather than a fixture.
CHART_ENCODINGS: dict[ChartType, dict[str, str]] = {
    ChartType.bar: {"x": "genotype", "y": "expr_fpkm", "hue": "condition"},
    ChartType.stacked_bar: {"x": "genotype", "y": "expr_fpkm", "hue": "condition"},
    ChartType.line: {"x": "time_h", "y": "od600", "hue": "genotype"},
    ChartType.scatter: {"x": "expr_fpkm", "y": "od600", "hue": "genotype"},
    ChartType.box: {"x": "condition", "y": "expr_fpkm", "hue": "genotype"},
    ChartType.heatmap: {"x": "condition", "y": "expr_fpkm", "hue": "genotype"},
}

GENOTYPES = ("WT", "dpsA", "rpoS", "hfq")
CONDITIONS = ("LB", "M9", "M9+NaCl")
TIMES = (0.0, 6.0, 12.0, 18.0)


def seed_data_path(data_root: Path) -> Path:
    return data_root / "assets" / "templates" / "_seed.csv"


def write_seed_data(data_root: Path) -> Path:
    """A small deterministic table that supports every chart type."""
    path = seed_data_path(data_root)
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["sample,genotype,condition,time_h,expr_fpkm,od600,yerr"]
    index = 0
    for genotype_index, genotype in enumerate(GENOTYPES):
        for condition_index, condition in enumerate(CONDITIONS):
            for time_index, time in enumerate(TIMES):
                index += 1
                base = 40.0 + 18.0 * genotype_index + 10.0 * condition_index
                expr = base + 6.0 * time_index
                od = 0.15 + 0.08 * genotype_index + 0.03 * time_index
                rows.append(
                    f"S{index:03d},{genotype},{condition},{time:g},{expr:.2f},{od:.3f},"
                    f"{max(1.0, expr * 0.08):.2f}"
                )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def build_template_page(
    *,
    preset: str,
    chart: str,
    backend: str,
    code: str,
    code_path: str,
    code_sha256: str,
    lint_ok: bool,
    data_columns: list[str],
) -> str:
    front = {
        "type": "template",
        "title": f"{chart} — {backend} — {preset} (verified builtin template)",
        "chart_type": chart,
        "backend": backend,
        "preset": preset,
        "reproduction_level": "L1",
        "verified": lint_ok,
        "code_sha256": code_sha256,
        "code_path": code_path,
        "pipeline_version": PIPELINE_VERSION,
        "seeded_at": datetime.now(UTC).date().isoformat(),
        "tags": "template,builtin,verified",
    }
    lines = ["---"]
    for key, value in front.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.extend(["---", ""])
    lines.append(f"# {chart} chart — {preset} ({backend})")
    lines.append("")
    lines.append(
        f"Verified builtin template: lint-clean render, deterministic emission "
        f"(pipeline {PIPELINE_VERSION}). Required columns: {', '.join(data_columns)}."
    )
    lines.append("")
    lines.append("## Script")
    lines.append("")
    fence = "python" if backend == "python" else "r"
    lines.append(f"```{fence}")
    lines.append(code.rstrip())
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


@dataclass
class SeedSummary:
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "written": self.written,
            "skipped": self.skipped,
            "failed": [{"slug": slug, "error": error} for slug, error in self.failed],
            "counts": {
                "written": len(self.written),
                "skipped": len(self.skipped),
                "failed": len(self.failed),
            },
        }


def seed_templates(
    kb: KnowledgeBase,
    *,
    data_root: Path,
    presets: list[str] | None = None,
    backends: tuple[str, ...] = ("python", "r"),
    force: bool = False,
    progress: Callable[[str], None] | None = None,
) -> SeedSummary:
    data_path = write_seed_data(data_root)
    schema = describe_data(str(data_path))
    summary = SeedSummary()
    chosen_presets = presets or preset_names()
    for backend in backends:
        for preset in chosen_presets:
            for chart, encoding in CHART_ENCODINGS.items():
                slug = template_slug(preset, chart.value, backend)
                spec = ChartSpec(
                    chart_type=chart,
                    preset=preset,
                    backend=backend,  # type: ignore[arg-type]
                    formats=["pdf"],
                    x=encoding["x"],
                    y=encoding["y"],
                    hue=encoding["hue"],
                )
                try:
                    result = render_spec(
                        schema,
                        spec,
                        out_dir=data_root
                        / "assets"
                        / "templates"
                        / preset
                        / f"{chart.value}-{backend}",
                        source="builtin_templates",
                    )
                except Exception as exc:  # noqa: BLE001 - one broken template must not stop seeding
                    summary.failed.append((slug, f"{type(exc).__name__}: {exc}"))
                    continue
                if not result.lint.ok:
                    summary.failed.append((slug, "lint failed: " + result.lint.format_text()))
                    continue
                relative = template_code_relpath(preset, chart.value, backend)
                stable_path = data_root / relative
                stable_path.parent.mkdir(parents=True, exist_ok=True)
                code = Path(result.code_path).read_text(encoding="utf-8")
                stable_path.write_text(code, encoding="utf-8")
                code_sha = hashlib.sha256(code.encode()).hexdigest()
                existing = try_get_page(kb, slug)
                if not force and existing is not None:
                    front = existing.get("frontmatter") or {}
                    if str(front.get("code_sha256") or "") == code_sha:
                        summary.skipped.append(slug)
                        continue
                markdown = build_template_page(
                    preset=preset,
                    chart=chart.value,
                    backend=backend,
                    code=code,
                    code_path=relative,
                    code_sha256=code_sha,
                    lint_ok=result.lint.ok,
                    data_columns=list(encoding.values()),
                )
                kb.put_page(slug, markdown, reason="verified builtin template (gaxis kb seed)")
                summary.written.append(slug)
                if progress:
                    progress(slug)
    return summary
