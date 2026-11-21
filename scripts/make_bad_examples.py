"""Generate deliberately bad figures for design-judge calibration.

These are the counterexamples a vision judge must rank below real journal figures:
default-matplotlib look, rainbow palettes, 3-D, oversized pies, heavy grids, missing
labels/units, clipped axes, Excel-ish shadows, and a table screenshot.

    pixi run python scripts/make_bad_examples.py --out data/corpus/golden/bad
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _bar_default(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(5, 3.2))
    axis.bar(["A", "B", "C", "D"], [3, 7, 2, 9])
    figure.savefig(path)
    plt.close(figure)


def _rainbow_bars(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(5, 3.2))
    axis.bar(range(10), [i + 1 for i in range(10)], color=plt.cm.jet([i / 10 for i in range(10)]))
    figure.savefig(path)
    plt.close(figure)


def _pie_rainbow(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(4, 4))
    axis.pie(
        [12, 3, 8, 2, 6, 1, 4, 2, 3, 1, 2, 1],
        colors=plt.cm.jet([i / 12 for i in range(12)]),
    )
    figure.savefig(path)
    plt.close(figure)


def _heavy_grid(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(5, 3.2))
    axis.plot([1, 2, 3, 4], [2, 5, 3, 6], color="#cc0000", linewidth=3)
    axis.grid(True, which="both", linewidth=1.2)
    axis.minorticks_on()
    figure.savefig(path)
    plt.close(figure)


def _clipped_axis_no_labels(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(5, 3.2))
    axis.bar(["A", "B", "C"], [98, 99, 97])
    axis.set_ylim(96.5, 99.5)
    axis.set_xticks([])
    axis.set_xlabel("")
    axis.set_ylabel("")
    figure.savefig(path)
    plt.close(figure)


def _three_d(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    figure = plt.figure(figsize=(5, 3.6))
    axis = figure.add_subplot(111, projection="3d")
    x = np.arange(4)
    axis.bar3d(x, [0, 0, 0, 0], 0, 0.6, 0.6, [3, 7, 2, 9], color=plt.cm.jet(x / 4))
    figure.savefig(path)
    plt.close(figure)


def _excel_style(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(5, 3.2), facecolor="#bfd7ea")
    axis.bar(
        ["A", "B", "C"],
        [3, 7, 5],
        color=["#ff0000", "#00ff00", "#0000ff"],
        edgecolor="black",
        linewidth=2,
        hatch="//",
    )
    axis.grid(True, linewidth=1.5)
    axis.set_facecolor("#e8f0f7")
    figure.savefig(path)
    plt.close(figure)


def _table_screenshot(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(6, 3.6))
    axis.axis("off")
    rows = [[f"gene_{i}", f"{i * 3.7:.1f}", f"{i % 4}", f"pathway_{i % 5}"] for i in range(14)]
    table = axis.table(
        cellText=rows,
        colLabels=["gene", "log2FC", "n", "pathway"],
        loc="center",
        cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(6)
    figure.savefig(path)
    plt.close(figure)


BAD_EXAMPLES = {
    "bad-01-default-matplotlib": _bar_default,
    "bad-02-rainbow-bars": _rainbow_bars,
    "bad-03-pie-rainbow": _pie_rainbow,
    "bad-04-heavy-grid": _heavy_grid,
    "bad-05-clipped-axis": _clipped_axis_no_labels,
    "bad-06-three-d": _three_d,
    "bad-07-excel-style": _excel_style,
    "bad-08-table-screenshot": _table_screenshot,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("data/corpus/golden/bad"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, builder in BAD_EXAMPLES.items():
        target = args.out / f"{name}.png"
        builder(target)
        print(f"wrote {target}")


if __name__ == "__main__":
    main()
