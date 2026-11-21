"""Spec inference: from a profiled table to a defensible default chart."""

from __future__ import annotations

from ..models.schema import ColumnKind, DataSchema
from ..models.spec import ChartSpec, ChartType

MAX_CATEGORIES_FOR_BAR = 12
MAX_HUE_LEVELS = 8
GROUPED_CHARTS = (
    ChartType.bar,
    ChartType.stacked_bar,
    ChartType.line,
    ChartType.scatter,
    ChartType.box,
)


def humanize(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").strip()


def categorical_candidates(schema: DataSchema) -> list[str]:
    """Most informative factor first; id-like columns (one value per row) are skipped.

    The x axis gets the factor with more levels, hue the one with fewer, so a
    grouped bar does not stack 12 hues into an unreadable legend.
    """
    profiles = schema.of_kind(ColumnKind.categorical, ColumnKind.boolean)
    useful = [c for c in profiles if c.n_unique < schema.n_rows or schema.n_rows <= 2]
    return [c.name for c in sorted(useful, key=lambda c: c.n_unique, reverse=True)]


def _kind(schema: DataSchema, name: str | None) -> ColumnKind | None:
    profile = schema.column(name) if name else None
    return profile.kind if profile else None


def suggest_chart_type(
    schema: DataSchema, x: str | None, y: str | None, hue: str | None = None
) -> ChartType:
    if y is None:
        return ChartType.bar
    x_kind = _kind(schema, x)
    if x_kind is ColumnKind.numeric:
        return ChartType.scatter if y else ChartType.line
    if x_kind in (ColumnKind.categorical, ColumnKind.boolean, ColumnKind.datetime):
        if x and schema.n_unique(x) > MAX_CATEGORIES_FOR_BAR:
            return ChartType.box
        return ChartType.bar
    return ChartType.bar


def infer_spec(
    schema: DataSchema,
    *,
    chart_type: ChartType | None = None,
    x: str | None = None,
    y: str | None = None,
    hue: str | None = None,
    yerr: str | None = None,
    preset: str = "default",
    palette: str | None = None,
    backend: str = "python",
    width_mm: float | None = None,
    height_mm: float | None = None,
    dpi: int = 600,
    formats: list[str] | None = None,
    annotate_values: bool = False,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
) -> ChartSpec:
    """Fill every unset encoding from the schema. Explicit user choices always win."""
    categorical = categorical_candidates(schema)
    numeric = schema.numeric_columns
    x_col = x or (categorical[0] if categorical else (numeric[0] if numeric else None))
    chart = chart_type or suggest_chart_type(schema, x_col, y, hue)
    y_col = y
    if y_col is None and numeric:
        # A numeric measure beats counting rows; counts are the last resort.
        y_col = next((c for c in numeric if c != x_col), numeric[0])
    hue_col = hue
    if hue_col is None and chart in GROUPED_CHARTS and categorical:
        candidate = next((c for c in categorical if c != x_col), None)
        if candidate and schema.n_unique(candidate) <= MAX_HUE_LEVELS:
            hue_col = candidate
    return ChartSpec(
        chart_type=chart,
        x=x_col,
        y=y_col,
        hue=hue_col,
        yerr=yerr,
        title=title,
        xlabel=xlabel if xlabel is not None else (humanize(x_col) if x_col else None),
        ylabel=ylabel if ylabel is not None else (humanize(y_col) if y_col else "count"),
        preset=preset,
        palette=palette,
        backend=backend,  # type: ignore[arg-type]
        width_mm=width_mm,
        height_mm=height_mm,
        dpi=dpi,
        formats=formats or ["pdf", "png"],
        annotate_values=annotate_values,
    )
