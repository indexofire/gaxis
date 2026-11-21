"""ChartReproManifest -> gbrain page.

Pages are a **derived, rebuildable index**: manifests stay authoritative, so a page
can always be regenerated and a brain can be wiped without losing anything. The page
carries filterable frontmatter (chart type, reproduction level, journal preset) and a
body with the text a human or an LLM would actually search: caption, citing
paragraph, visual grammar, code summary.
"""

from __future__ import annotations

from ..models.paper import ChartReproManifest

CHART_SYNONYMS: dict[str, tuple[str, ...]] = {
    "bar": ("bar chart", "column chart", "柱状图", "条形图"),
    "stacked_bar": ("stacked bar chart", "堆叠柱状图", "堆积柱状图"),
    "line": ("line chart", "line plot", "rarefaction curve", "growth curve", "折线图", "曲线图"),
    "scatter": ("scatter plot", "散点图", "相关图"),
    "box": ("box plot", "箱线图", "箱型图"),
    "heatmap": ("heatmap", "heat map", "热图", "热力图"),
}


def page_slug(source: str, manifest_id: str) -> str:
    return f"{source}:{manifest_id.replace('/', '-').replace(' ', '-')}"


def _yaml_value(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\n", " ").strip()
    if any(char in text for char in ":#{}[]\"'") or text.startswith(("*", "&", "!", "|", ">")):
        escaped = text.replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _frontmatter(manifest: ChartReproManifest) -> dict[str, object]:
    grammar = manifest.visual_grammar
    reproduction = manifest.reproduction
    return {
        "type": "analysis",
        "title": f"{manifest.figure_ref} — {manifest.caption[:80]}".strip(" —"),
        "asset_id": manifest.manifest_id,
        "paper_id": manifest.paper_id,
        "paper_title": manifest.paper_title,
        "doi": manifest.doi,
        "figure_ref": manifest.figure_ref,
        "chart_type": grammar.chart_type.value if grammar.chart_type else None,
        "reproduction_level": reproduction.level,
        "reproduction_method": reproduction.method if reproduction.method != "none" else None,
        "reproduction_model": reproduction.model,
        "sandbox_run_status": reproduction.sandbox_run_status,
        "visual_similarity": reproduction.visual_similarity,
        "chart_quality_score": manifest.chart_quality_score,
        "design_score": manifest.design.score if manifest.design else None,
        "design_tier": manifest.design.tier if manifest.design else None,
        "design_model": manifest.design.method if manifest.design else None,
        "usefulness_score": manifest.usefulness.score if manifest.usefulness else None,
        "aesthetic_score": manifest.design.aesthetic if manifest.design else None,
        "visualization_score": manifest.design.visualization if manifest.design else None,
        "chart_like": manifest.design.features.chart_like if manifest.design else None,
        "colorblind_safe": (manifest.design.features.colorblind_safe if manifest.design else None),
        "image_path": manifest.chart_file or None,
        "code_path": manifest.code_candidates[0].code_path if manifest.code_candidates else None,
        "code_sha256": None,  # reproduced code hashes live per-run; keep the field reserved
        "license": next((c.license for c in manifest.code_candidates if c.license), None),
        "tags": "chart-asset,paper-figure",
    }


def build_page(manifest: ChartReproManifest, *, source: str) -> tuple[str, str]:
    """Return (slug, markdown)."""
    front = _frontmatter(manifest)
    lines = ["---"]
    for key, value in front.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.append("---")
    lines.append("")

    caption = manifest.caption or "(no caption extracted)"
    title = caption.split(". ")[0][:120]
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Caption.** {caption}")
    lines.append("")
    if manifest.citing_paragraph:
        lines.append(f"**Citing paragraph.** {manifest.citing_paragraph}")
        lines.append("")

    grammar = manifest.visual_grammar
    chart_type = grammar.chart_type.value if grammar.chart_type else None
    synonyms = CHART_SYNONYMS.get(chart_type or "", ())
    grammar_bits = []
    if chart_type:
        grammar_bits.append(f"chart type: {chart_type}")
    if synonyms:
        grammar_bits.append("also known as: " + ", ".join(synonyms))
    grammar_bits.extend(grammar.notes)
    if manifest.geometry is not None:
        grammar_bits.append(
            f"extracted from page {manifest.geometry.page} "
            f"({'vector' if manifest.geometry.is_vector else 'raster'})"
        )
    if grammar_bits:
        lines.append("**Visual grammar.** " + "; ".join(grammar_bits) + ".")
        lines.append("")

    if manifest.design is not None:
        design = manifest.design
        aesthetic = f"{design.aesthetic:.2f}" if design.aesthetic is not None else "not judged"
        score = f"{design.score:.2f}" if design.score is not None else "not judged"
        bits = [
            f"design {score} (aesthetic {aesthetic}, visualization {design.visualization:.2f})",
            f"tier {design.tier or 'unassigned'}",
            f"{design.features.n_colours} chromatic colours",
        ]
        if design.features.colorblind_safe is False:
            bits.append("palette not colour-blind safe")
        if design.features.min_font_pt is not None:
            bits.append(f"labels {design.features.min_font_pt:.1f} pt")
        if design.features.caption_signals:
            bits.append("signals: " + ", ".join(design.features.caption_signals))
        lines.append("**Design.** " + "; ".join(bits) + ".")
        lines.append("")

    if manifest.usefulness is not None:
        lines.append(
            "**Usefulness.** "
            f"{manifest.usefulness.score:.2f} — " + "; ".join(manifest.usefulness.notes) + "."
        )
        lines.append("")

    if manifest.usefulness is not None:
        lines.append(
            "**Usefulness.** "
            f"{manifest.usefulness.score:.2f} — " + "; ".join(manifest.usefulness.notes) + "."
        )
        lines.append("")

    reproduction = manifest.reproduction
    lines.append(
        "**Reproduction.** "
        f"level {reproduction.level}; sandbox {reproduction.sandbox_run_status}"
        + (
            f"; visual similarity {reproduction.visual_similarity:.2f}"
            if reproduction.visual_similarity is not None
            else ""
        )
        + (f"; {reproduction.failure_reason}" if reproduction.failure_reason else "")
        + "."
    )
    lines.append("")

    if manifest.code_candidates:
        candidate = manifest.code_candidates[0]
        deps = ", ".join(candidate.dependency_hints) or "unknown"
        lines.append(
            f"**Code.** {candidate.code_path} ({candidate.language}); dependencies: {deps}"
            + (f"; licence {candidate.license}" if candidate.license else "")
            + "."
        )
        lines.append("")

    if manifest.chart_file:
        lines.append(
            f"**Image.** `{manifest.chart_file}` — stored as a file next to the assets; "
            "a multimodal host opens it directly, the brain only stores the path."
        )
    else:
        lines.append(
            "**Image.** Not present in the source PDF (pre-proof or separate figure files)."
        )
    lines.append("")

    provenance = [f"paper {manifest.paper_id}"]
    if manifest.doi:
        provenance.append(f"doi {manifest.doi}")
    if manifest.paper_title:
        provenance.append(f'title "{manifest.paper_title}"')
    lines.append("**Provenance.** " + "; ".join(provenance) + ".")
    return page_slug(source, manifest.manifest_id), "\n".join(lines).strip() + "\n"
