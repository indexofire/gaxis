"""Brief -> ChartPlan: deterministic, bilingual, no LLM call.

Service flow 1 starts with a sentence ("a grouped bar chart with error bars for a
Nature Microbiology submission"), not a tidy table. The plan is what the host LLM
converges on with the user before any data exists: chart type, journal preset,
style notes, the columns the table will need, and the open questions worth asking.

Determinism is deliberate: the same brief must produce the same plan, and a host
must be able to explain every field it got (ADR-08 applies to plans too).
"""

from __future__ import annotations

from collections.abc import Iterable

from ..models.spec import ChartSpec, ChartType
from ..models.tools import ChartPlan, ColumnRole
from ..style.palettes import PALETTES
from ..style.presets import preset_names

# Order matters: more specific chart families are tested before their parents.
CHART_KEYWORDS: list[tuple[ChartType, tuple[str, ...]]] = [
    (ChartType.stacked_bar, ("stacked bar", "stacked column", "堆叠", "堆积", "叠加柱")),
    (
        ChartType.bar,
        ("bar chart", "bar plot", "barplot", "column chart", "柱状图", "条形图", "柱形图"),
    ),
    (
        ChartType.line,
        (
            "line chart",
            "line plot",
            "curve",
            "rarefaction",
            "growth curve",
            "趋势图",
            "折线",
            "曲线",
        ),
    ),
    (ChartType.scatter, ("scatter", "散点", "相关图")),
    (ChartType.box, ("box plot", "boxplot", "violin", "箱线", "箱型", "小提琴")),
    (
        ChartType.heatmap,
        ("heatmap", "heat map", "热图", "热力图", "聚类热图"),
    ),
]

PRESET_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("nature_microbiology", ("nature microbiology", "自然微生物学")),
    ("cell_host_microbe", ("cell host", "cell host & microbe", "宿主与微生物")),
    ("microbial_genomics", ("microbial genomics", "微生物基因组学")),
    ("isme", ("isme",)),
    ("asm", ("mbio", "aem", "applied and environmental", "microbiology spectrum", "asm journal")),
    ("nature", ("nature", "自然")),
]


def _hits(text: str, tokens: Iterable[str]) -> int:
    return sum(1 for token in tokens if token in text)


def _detect_chart(text: str) -> tuple[ChartType | None, int]:
    best: tuple[ChartType | None, int] = (None, 0)
    for chart, tokens in CHART_KEYWORDS:
        hits = _hits(text, tokens)
        if hits > best[1]:
            best = (chart, hits)
    return best


def detect_chart_type(text: str) -> ChartType | None:
    """Public wrapper used by paper parsing to guess a figure type from its caption."""
    return _detect_chart(text.lower())[0]


def _detect_preset(text: str) -> str | None:
    for preset, tokens in PRESET_KEYWORDS:
        if _hits(text, tokens):
            return preset if preset in preset_names() else None
    return None


def _detect_palette(text: str) -> str | None:
    for name in PALETTES:
        if name in text:
            return name
    if _hits(text, ("colorblind", "colour-blind", "color-blind", "色盲", "无障碍")):
        return "okabe_ito"
    if _hits(text, ("grayscale", "greyscale", "灰度", "黑白")):
        return "greys"
    return None


def _detect_backend(text: str) -> str | None:
    if _hits(text, ("ggplot", "ggplot2", "rscript", "r 语言", "r语言")):
        return "r"
    if _hits(text, ("matplotlib", "python", "seaborn")):
        return "python"
    return None


def required_columns(chart: ChartType) -> list[ColumnRole]:
    """Column roles the user's table must provide, in role terms."""
    grouped = ColumnRole(
        role="hue", kind="categorical", hint="grouping factor, 2-8 levels (colour/fill)"
    )
    if chart is ChartType.scatter:
        return [
            ColumnRole(role="x", kind="numeric", hint="continuous x variable"),
            ColumnRole(role="y", kind="numeric", hint="continuous y variable"),
            grouped,
        ]
    if chart is ChartType.line:
        return [
            ColumnRole(role="x", kind="numeric", hint="ordered variable (time, depth, dose)"),
            ColumnRole(role="y", kind="numeric", hint="measurement, one row per observation"),
            grouped,
        ]
    if chart in (ChartType.box, ChartType.heatmap):
        return [
            ColumnRole(role="x", kind="categorical", hint="2-12 groups"),
            ColumnRole(role="y", kind="numeric", hint="measurement (heatmap: value per cell)"),
            grouped,
        ]
    return [
        ColumnRole(role="x", kind="categorical", hint="2-12 groups"),
        ColumnRole(
            role="y", kind="numeric", hint="measurement per observation (omit to count rows)"
        ),
        grouped,
    ]


def _style_notes(text: str) -> list[str]:
    notes: list[str] = []
    error_tokens = (
        "error bar",
        "errorbar",
        "误差棒",
        "误差线",
        "置信区间",
        "confidence interval",
        "±",
    )
    if _hits(text, error_tokens):
        notes.append(
            "error bars: mean ± SD across replicates by default; pass a `yerr` column "
            "to supply SEM or 95% CI instead"
        )
    if _hits(text, ("no grid", "无网格", "不要网格", "去掉网格")):
        notes.append("grid off (already the default for every preset)")
    elif _hits(text, ("grid", "网格")):
        notes.append("grid requested: enable via the renderer, journals usually prefer none")
    if _hits(text, ("log scale", "log10", "对数")):
        notes.append("log-transformed axis requested: transform the measure before rendering")
    if _hits(text, ("panel", "子图", "多面板", "a/b/c")):
        notes.append("multi-panel (A/B/C) layout requested: compose panels before export (M4)")
    if _hits(text, ("legend", "图例")):
        notes.append("legend outside the axes on the right (matches both backends)")
    if _hits(text, ("horizontal", "横向", "水平")):
        notes.append("horizontal orientation requested: current templates are vertical-only")
    return notes


def _questions(
    chart: ChartType | None,
    preset: str | None,
    text: str,
    *,
    palette: str | None,
    backend: str | None,
) -> list[str]:
    questions: list[str] = []
    if chart is None:
        questions.append("Which chart type: bar, stacked bar, line, scatter, box, or heatmap?")
    if preset is None:
        questions.append(
            "Which journal or column width should set geometry? "
            f"available presets: {', '.join(preset_names())}"
        )
    if _hits(text, ("误差", "error", "置信", "confidence", "±")):
        questions.append("Error bars: SD, SEM, or 95% CI? (and how many replicates per group)")
    if _hits(text, ("panel", "子图", "多面板")):
        questions.append("Panel layout: how many panels, and do they share axes or a legend?")
    if palette is None:
        questions.append(
            "Colour palette: colour-blind-safe default (Okabe-Ito) or journal brand colours?"
        )
    if backend is None:
        questions.append("Deliverable language: matplotlib (figure.py) or ggplot2 (figure.R)?")
    questions.append("Attach the table (CSV/TSV, one observation per row) or describe its columns")
    return questions


def build_plan(
    brief: str,
    *,
    preset: str | None = None,
    backend: str | None = None,
) -> ChartPlan:
    text = brief.lower()
    chart, chart_hits = _detect_chart(text)
    detected_preset = preset or _detect_preset(text)
    palette = _detect_palette(text)
    detected_backend = backend or _detect_backend(text)
    chosen_chart = chart or ChartType.bar

    confidence = 0.3
    if chart is not None:
        confidence += 0.2 + min(0.05 * chart_hits, 0.1)
    if detected_preset:
        confidence += 0.15
    if detected_backend:
        confidence += 0.1
    if palette:
        confidence += 0.05

    return ChartPlan(
        brief=brief,
        spec=ChartSpec(
            chart_type=chosen_chart,
            preset=detected_preset or "default",
            palette=palette,
            backend=detected_backend or "python",  # type: ignore[arg-type]
            annotate_values=bool(_hits(text, ("annotate", "标注数值", "数值标注"))),
        ),
        required_columns=required_columns(chosen_chart),
        style_notes=_style_notes(text),
        open_questions=_questions(
            chart, detected_preset, text, palette=palette, backend=detected_backend
        ),
        confidence=round(min(confidence, 0.9), 2),
    )


def parse_preset_hint(brief: str) -> str | None:
    """Exposed for tests and for hosts that only need the journal guess."""
    return _detect_preset(brief.lower())
