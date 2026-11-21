"""Splitting a plate into single-figure candidates."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from gaxis.design import plate_blocks, split_plate


def _grid(path: Path, rows: int, cols: int) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(rows, cols, figsize=(6, 2.4 * rows), dpi=120)
    axes = axes.reshape(rows, cols)
    for row in range(rows):
        for col in range(cols):
            axes[row][col].bar(["A", "B"], [row + 1, col + 2])
            axes[row][col].set_title(f"r{row}c{col}")
    figure.subplots_adjust(hspace=0.5, wspace=0.35)
    figure.savefig(path, facecolor="white")
    plt.close(figure)
    return path


def test_two_by_two_plate_splits_into_four(tmp_path: Path) -> None:
    plate = _grid(tmp_path / "plate.png", 2, 2)
    assert len(plate_blocks(plate)) >= 3
    crops = split_plate(plate, tmp_path / "out")
    assert len(crops) >= 3
    assert all(crop.is_file() and crop.stat().st_size > 1000 for crop in crops)


def test_stacked_plate_splits_into_rows(tmp_path: Path) -> None:
    plate = _grid(tmp_path / "stack.png", 3, 1)
    crops = split_plate(plate, tmp_path / "out")
    assert len(crops) == 3


def test_single_figure_returns_one_crop(tmp_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(4, 2.6), dpi=150)
    axis.bar(["A", "B", "C"], [2, 5, 3])
    figure.savefig(tmp_path / "single.png", facecolor="white")
    plt.close(figure)
    crops = split_plate(tmp_path / "single.png", tmp_path / "out")
    assert len(crops) == 1
