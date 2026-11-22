"""Code emission: ChartSpec + DataSchema + Preset -> a standalone script.

The emitted script is the deliverable. gaxis is not imported by the generated
code, so what a user receives can be read, edited and submitted as-is.
"""

from __future__ import annotations

import json
import pprint
from importlib import resources
from pathlib import Path
from typing import Any

from .. import __version__
from ..models.schema import DataSchema
from ..models.spec import ChartSpec
from ..style.palettes import get_palette
from ..style.presets import Preset
from ..style.rc import build_rc, resolve_font, size_inches

SUPPORTED_CHARTS = (
    "bar",
    "stacked_bar",
    "line",
    "scatter",
    "box",
    "heatmap",
    "network",
    "tree",
)


def _template(name: str) -> str:
    return resources.files("gaxis.render").joinpath("templates", name).read_text(encoding="utf-8")


def _py(value: Any) -> str:
    return pprint.pformat(value, width=96, sort_dicts=False)


def _r(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def _docstring(spec: ChartSpec, preset: Preset, schema: DataSchema) -> str:
    y = spec.y or "counts"
    x = spec.x or "level"
    grouped = f", grouped by {spec.hue}" if spec.hue else ""
    return (
        f"{spec.chart_type.value} chart of {y} by {x}{grouped} — {preset.label}; "
        f"data: {Path(schema.path).name}"
    )


def _common(*, spec: ChartSpec, preset: Preset, schema: DataSchema) -> dict[str, str]:
    return {
        "@DOCSTRING@": _docstring(spec, preset, schema),
        "@VERSION@": __version__,
        "@DATA_NAME@": Path(schema.path).name,
        "@PRESET_LABEL@": preset.label,
        "@BASE_PT@": f"{preset.base_font_pt:g}",
        "@LABEL_PT@": f"{preset.label_font_pt:g}",
        "@TITLE_PT@": f"{preset.title_font_pt:g}",
        "@SPINE_WIDTH@": f"{preset.spine_width_pt:g}",
        "@LINE_WIDTH@": f"{preset.line_width_pt:g}",
        "@MARKER_SIZE@": f"{preset.marker_size_pt:g}",
        "@DPI@": str(spec.dpi),
    }


def _fill(template: str, mapping: dict[str, str]) -> str:
    for key in sorted(mapping, key=len, reverse=True):
        template = template.replace(key, mapping[key])
    return template


def emit_code(
    *,
    spec: ChartSpec,
    schema: DataSchema,
    preset: Preset,
    width_mm: float,
    height_mm: float,
    data_path: Path,
    out_dir: Path,
    stem: str,
) -> str:
    if spec.chart_type.value not in SUPPORTED_CHARTS:
        raise ValueError(f"no template for chart type {spec.chart_type}")
    chart = spec.chart_type.value
    palette = get_palette(spec.palette or preset.palette)
    rc = build_rc(preset, width_mm=width_mm, height_mm=height_mm, dpi=spec.dpi)
    fig_w, fig_h = size_inches(width_mm, height_mm)
    mapping = _common(spec=spec, preset=preset, schema=schema)
    mapping.update(
        {"@DATA_PATH@": repr(str(data_path)), "@OUT_DIR@": repr(str(out_dir)), "@STEM@": repr(stem)}
    )
    if spec.backend == "python":
        mapping.update(
            {
                "@DELIM@": repr(schema.delimiter),
                "@SPEC@": _py(
                    {
                        "chart_type": chart,
                        "x": spec.x,
                        "y": spec.y,
                        "hue": spec.hue,
                        "yerr": spec.yerr,
                        "weight": spec.weight,
                        "title": spec.title,
                        "xlabel": spec.xlabel,
                        "ylabel": spec.ylabel,
                        "annotate": spec.annotate_values,
                        "formats": spec.formats,
                    }
                ),
                "@COLORS@": _py(palette.colors),
                "@RC@": _py(rc),
                "@FIG_W@": f"{fig_w:.5f}",
                "@FIG_H@": f"{fig_h:.5f}",
                "@WIDTH_MM@": f"{width_mm:g}",
                "@HEIGHT_MM@": f"{height_mm:g}",
            }
        )
        return _fill(
            _template("python_header.tpl") + "\n" + _template(f"python_{chart}.tpl"), mapping
        )
    font = resolve_font(tuple(preset.font_family)) or "sans"
    mapping.update(
        {
            "@SEP@": _r(schema.delimiter),
            "@FONT@": _r(font),
            "@X@": _r(spec.x),
            "@Y@": _r(spec.y),
            "@HUE@": _r(spec.hue),
            "@YERR@": _r(spec.yerr),
            "@WEIGHT@": _r(spec.weight),
            "@TITLE@": _r(spec.title),
            "@XLABEL@": _r(spec.xlabel),
            "@YLABEL@": _r(spec.ylabel),
            "@ANNOTATE@": "TRUE" if spec.annotate_values else "FALSE",
            "@FORMATS@": ", ".join(_r(f) for f in spec.formats),
            "@COLORS@": ", ".join(_r(c) for c in palette.colors),
            "@WIDTH_MM@": f"{width_mm:g}",
            "@HEIGHT_MM@": f"{height_mm:g}",
            "@FIG_W@": f"{width_mm:g}",
            "@FIG_H@": f"{height_mm:g}",
        }
    )
    return _fill(_template("r_header.tpl") + "\n" + _template(f"r_{chart}.tpl"), mapping)
