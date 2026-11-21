"""Multi-panel composition: place rendered panels on one page, keeping vector content.

Panels are rendered first (each with its own standalone script + manifest); composition
only arranges the finished PDFs, so nothing is re-drawn and the evidence chain stays
intact (each panel's code hash is recorded in the composition manifest).

Backend-agnostic on purpose: matplotlib and ggplot2 both emit PDF, and PyMuPDF can place
those pages without rasterising.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from .errors import GaxisError
from .models.composition import CompositionManifest, PanelRef
from .models.manifest import FigureManifest
from .style.presets import load_preset

MM_TO_PT = 72.0 / 25.4

MARGIN_MM = 2.0
GUTTER_MM = 2.0
CELL_ASPECT = 0.78


@dataclass(frozen=True)
class PanelSource:
    manifest_id: str
    pdf: Path
    code_sha256: str


def _panel_pdf(manifest: FigureManifest, data_root: Path) -> Path:
    for output in manifest.outputs:
        if output.format == "pdf":
            path = Path(output.path)
            return path if path.is_absolute() else data_root / path
    raise GaxisError(
        "panel_not_vector",
        f"{manifest.figure_id} has no PDF output; compose needs vector panels",
        hint="re-render the panel with formats including 'pdf'",
    )


def collect_panels(manifests: list[FigureManifest], data_root: Path) -> list[PanelSource]:
    sources = []
    for manifest in manifests:
        pdf = _panel_pdf(manifest, data_root)
        if not pdf.is_file():
            raise GaxisError("panel_missing", f"panel PDF not found: {pdf}")
        sources.append(
            PanelSource(
                manifest_id=manifest.figure_id,
                pdf=pdf,
                code_sha256=manifest.code_sha256,
            )
        )
    return sources


def _grid(count: int, layout: tuple[int, int] | None) -> tuple[int, int]:
    if layout:
        rows, cols = layout
        if rows * cols < count:
            raise GaxisError(
                "bad_layout",
                f"layout {rows}x{cols} has {rows * cols} cells for {count} panels",
                hint="increase the grid or pass a larger layout",
            )
        return rows, cols
    if count <= 3:
        return 1, count
    if count == 4:
        return 2, 2
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    return rows, cols


@dataclass(frozen=True)
class PageGeometry:
    rows: int
    cols: int
    width_mm: float
    height_mm: float
    cell_w_mm: float
    cell_h_mm: float


def page_geometry(
    count: int,
    *,
    preset_name: str,
    layout: tuple[int, int] | None = None,
    width_mm: float | None = None,
    height_mm: float | None = None,
) -> PageGeometry:
    """Page and cell size in millimetres, shared by composition and panel re-render."""
    preset = load_preset(preset_name)
    rows, cols = _grid(count, layout)
    width_mm = width_mm or preset.width_double_mm
    if height_mm is None:
        height_mm = round(width_mm * (rows / cols) * CELL_ASPECT, 1)
    cell_w_mm = (width_mm - 2 * MARGIN_MM - (cols - 1) * GUTTER_MM) / cols
    cell_h_mm = (height_mm - 2 * MARGIN_MM - (rows - 1) * GUTTER_MM) / rows
    return PageGeometry(rows, cols, width_mm, height_mm, cell_w_mm, cell_h_mm)


def compose_panels(
    sources: list[PanelSource],
    *,
    out_dir: Path,
    preset_name: str,
    layout: tuple[int, int] | None = None,
    width_mm: float | None = None,
    height_mm: float | None = None,
    labels: bool = True,
    dpi: int = 600,
    composition_id: str | None = None,
    uniform: bool = False,
) -> CompositionManifest:
    import fitz  # PyMuPDF

    preset = load_preset(preset_name)
    geometry = page_geometry(
        len(sources), preset_name=preset_name, layout=layout, width_mm=width_mm, height_mm=height_mm
    )
    rows, cols = geometry.rows, geometry.cols
    width_mm, height_mm = geometry.width_mm, geometry.height_mm
    out_dir.mkdir(parents=True, exist_ok=True)
    identifier = (
        composition_id
        or hashlib.sha256(
            (
                ":".join(source.manifest_id for source in sources) + f":{rows}x{cols}:{preset_name}"
            ).encode()
        ).hexdigest()[:10]
    )
    pdf_path = out_dir / f"composition-{identifier}.pdf"

    margin = MARGIN_MM * MM_TO_PT
    gutter = GUTTER_MM * MM_TO_PT
    page_width = width_mm * MM_TO_PT
    page_height = height_mm * MM_TO_PT
    cell_w = (page_width - 2 * margin - (cols - 1) * gutter) / cols
    cell_h = (page_height - 2 * margin - (rows - 1) * gutter) / rows

    doc = fitz.open()
    page = doc.new_page(width=page_width, height=page_height)
    letter_map = "ABCDEFGH"
    panel_refs: list[PanelRef] = []
    for index, source in enumerate(sources):
        row, col = divmod(index, cols)
        x0 = margin + col * (cell_w + gutter)
        y0 = margin + row * (cell_h + gutter)
        label = letter_map[index] if labels and index < len(letter_map) else ""
        label_offset = 10 if label else 0
        rect = fitz.Rect(x0, y0 + label_offset, x0 + cell_w, y0 + cell_h)
        with fitz.open(source.pdf) as panel_doc:
            page.show_pdf_page(rect, panel_doc, 0, keep_proportion=True)
        if label:
            page.insert_text(
                (x0 + 1, y0 + 8),
                label,
                fontsize=8,
                fontname="helv",
            )
        panel_refs.append(
            PanelRef(
                manifest_id=source.manifest_id,
                label=label,
                source_file=str(source.pdf),
                code_sha256=source.code_sha256,
            )
        )
    doc.save(pdf_path)
    doc.close()

    png_path: Path | None = None
    with fitz.open(pdf_path) as rendered:
        pixmap = rendered[0].get_pixmap(dpi=dpi)
        png_path = pdf_path.with_suffix(".png")
        pixmap.save(png_path)

    from .style.lint import lint_outputs, measure_output

    lint = lint_outputs(
        [pdf_path, png_path],
        preset=preset,
        spec=_spec_stub(preset_name),
        expected_width_mm=width_mm,
        expected_height_mm=height_mm,
    )
    manifest = CompositionManifest(
        composition_id=f"composition-{identifier}",
        panels=panel_refs,
        layout=(rows, cols),
        preset=preset_name,
        width_mm=width_mm,
        height_mm=height_mm,
        output_pdf=str(pdf_path),
        output_png=str(png_path) if png_path else None,
        lint=lint,
        uniform=uniform,
    )
    (out_dir / f"composition-{identifier}.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    measure_output(pdf_path)  # surface geometry problems during composition, not later
    return manifest


def _spec_stub(preset_name: str):
    """Lint needs a ChartSpec; a minimal one is enough for a composition."""
    from .models.spec import ChartSpec

    return ChartSpec(preset=preset_name, formats=["pdf", "png"])
