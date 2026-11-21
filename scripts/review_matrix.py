"""Standalone acceptance review: render a chart x preset x backend matrix.

Produces, under ``data/review``:

  <chart>-<preset>-<backend>/   figure + standalone script + manifest + lint
  REVIEW.md                     one table: geometry, lint, script path
  contact-sheet.png             every figure on one page, labelled

This is the artifact a human eyeballs before the project moves on to the
paper-side milestones. It is deliberately not part of `pixi run check`:
rendering 36 figures belongs in a review step, not in CI.

Usage:
    pixi run review                      # defaults: demo table, 6 charts, 3 presets, 2 backends
    pixi run python scripts/review_matrix.py --data my.tsv --presets asm
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from gaxis.errors import GaxisError
from gaxis.models.spec import ChartType
from gaxis.models.tools import RenderRequest
from gaxis.service import render

DEFAULT_DATA = Path("examples/demo/expr.tsv")
DEFAULT_OUT = Path("data/review")
DEFAULT_PRESETS = ("nature_microbiology", "asm", "cell_host_microbe")
DEFAULT_BACKENDS = ("python", "r")

# Encodings that exercise each chart type against the microbiology demo table.
ENCODINGS: dict[str, dict[str, object]] = {
    "bar": {"x": "genotype", "y": "expr_fpkm", "hue": "condition"},
    "stacked_bar": {"x": "genotype", "y": "expr_fpkm", "hue": "condition"},
    "line": {"x": "time_h", "y": "expr_fpkm", "hue": "genotype"},
    "scatter": {"x": "od600", "y": "expr_fpkm", "hue": "genotype"},
    "box": {"x": "genotype", "y": "expr_fpkm", "hue": "condition"},
    "heatmap": {"x": "genotype", "y": "expr_fpkm", "hue": "condition", "annotate_values": True},
}


@dataclass
class Cell:
    chart: str
    preset: str
    backend: str
    figure_id: str = ""
    png: Path | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    lint_errors: int = 0
    lint_warnings: int = 0
    lint_text: str = ""
    code_path: str = ""
    error: str = ""

    @property
    def label(self) -> str:
        if self.error:
            return "FAILED"
        geometry = f"{self.width_mm:.0f}x{self.height_mm:.0f}mm" if self.width_mm else "-"
        state = (
            "clean"
            if not self.lint_errors and not self.lint_warnings
            else (f"{self.lint_errors}E/{self.lint_warnings}W")
        )
        return f"{geometry}  {state}"


def render_cell(data: Path, preset: str, backend: str, chart: str, out_root: Path) -> Cell:
    cell = Cell(chart=chart, preset=preset, backend=backend)
    request = RenderRequest(
        data_path=str(data.resolve()),
        chart_type=ChartType(chart),
        preset=preset,
        backend=backend,  # type: ignore[arg-type]
        formats=["pdf", "png"],
        out_dir=str(out_root / f"{chart}-{preset}-{backend}"),
        **ENCODINGS[chart],  # type: ignore[arg-type]
    )
    try:
        result = render(request)
    except GaxisError as exc:
        cell.error = f"{exc.code}: {exc.message}"
        return cell
    cell.figure_id = result.figure_id
    cell.code_path = result.code_path
    cell.lint_errors = len(result.lint.errors)
    cell.lint_warnings = len(result.lint.warnings)
    cell.lint_text = result.lint.format_text()
    png = next((Path(o.path) for o in result.outputs if o.format == "png"), None)
    cell.png = png
    for output in result.outputs:
        if output.format in {"pdf", "svg"}:
            cell.width_mm = output.width_mm
            cell.height_mm = output.height_mm
    return cell


def contact_sheet(
    cells: list[Cell], path: Path, charts: list[str], columns: list[tuple[str, str]]
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    rows, cols = len(charts), len(columns)
    fig, axes = plt.subplots(rows, cols, figsize=(2.6 * cols, 2.2 * rows), squeeze=False)
    for row, chart in enumerate(charts):
        for col, (preset, backend) in enumerate(columns):
            ax = axes[row][col]
            ax.set_xticks([])
            ax.set_yticks([])
            cell = next(
                c for c in cells if c.chart == chart and c.preset == preset and c.backend == backend
            )
            if cell.png and cell.png.is_file():
                ax.imshow(mpimg.imread(cell.png))
                ax.set_title(f"{cell.label}", fontsize=6)
            else:
                ax.text(
                    0.5,
                    0.5,
                    cell.error or "no output",
                    ha="center",
                    va="center",
                    fontsize=5,
                    wrap=True,
                    transform=ax.transAxes,
                )
            if col == 0:
                ax.set_ylabel(chart, fontsize=8)
            if row == 0:
                ax.set_title(f"{preset}\n{backend}", fontsize=7)
    fig.suptitle("gaxis standalone review — rows: chart type, columns: journal preset x backend")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_report(cells: list[Cell], path: Path, data: Path) -> None:
    failures = [cell for cell in cells if cell.error]
    dirty = [cell for cell in cells if not cell.error and (cell.lint_errors or cell.lint_warnings)]
    lines = [
        "# Standalone review",
        "",
        f"Data: `{data}` · {len(cells)} renders · {len(failures)} failed · "
        f"{len(dirty)} with lint findings",
        "",
        "| chart | preset | backend | geometry | lint | code |",
        "|---|---|---|---|---|---|",
    ]
    for cell in cells:
        geometry = f"{cell.width_mm:.1f}x{cell.height_mm:.1f} mm" if cell.width_mm else "-"
        if cell.error:
            state = f"failed: {cell.error}"
        elif cell.lint_errors or cell.lint_warnings:
            state = cell.lint_text.replace("|", "\\|")
        else:
            state = "clean"
        lines.append(
            f"| {cell.chart} | {cell.preset} | {cell.backend} | {geometry} | {state} | "
            f"{cell.code_path or '-'} |"
        )
    lines += [
        "",
        "## How to review",
        "",
        "1. Open `contact-sheet.png`: each column is a journal preset, each row a chart type.",
        "2. Check per figure: axis labels/units, tick readability at print size, legend placement,",
        "   error-bar meaning (SD unless a `yerr` column is given), palette accessibility.",
        "3. Open one `figure.py` and one `figure.R`: they must read like hand-written publication",
        "   code (no gaxis imports, one obvious place to change columns).",
        "4. Confirm `manifest.json` carries `data.sha256`, `code_sha256` and the lint report.",
        "5. Anything that looks wrong is a template or preset bug, not a user error — record it.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--presets", nargs="+", default=list(DEFAULT_PRESETS))
    parser.add_argument("--backends", nargs="+", default=list(DEFAULT_BACKENDS))
    parser.add_argument("--charts", nargs="+", default=list(ENCODINGS))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.data.is_file():
        print(f"error: data file not found: {args.data}", file=sys.stderr)
        print("hint: `pixi run review` defaults to examples/demo/expr.tsv", file=sys.stderr)
        return 2

    cells: list[Cell] = []
    for chart in args.charts:
        for preset in args.presets:
            for backend in args.backends:
                cell = render_cell(args.data, preset, backend, chart, args.out)
                cells.append(cell)
                print(f"{chart:<12} {preset:<20} {backend:<7} {cell.label}")

    report = args.out / "REVIEW.md"
    sheet = args.out / "contact-sheet.png"
    write_report(cells, report, args.data)
    columns = [(preset, backend) for preset in args.presets for backend in args.backends]
    contact_sheet(cells, sheet, list(args.charts), columns)

    failures = [cell for cell in cells if cell.error]
    if args.json:
        rows = [cell.__dict__ | {"png": str(cell.png) if cell.png else None} for cell in cells]
        print(json.dumps(rows, indent=2, default=str))
    print(f"\nreport:  {report}")
    print(f"sheet:   {sheet}")
    print(f"failed:  {len(failures)}/{len(cells)}")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
