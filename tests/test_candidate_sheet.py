"""Candidate sheets for external curated figures (golden-set building)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from gaxis.design import build_candidate_sheet


def test_sheet_skips_broken_files_and_converts_jpeg(tmp_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    source = tmp_path / "src"
    source.mkdir()
    figure, axis = plt.subplots(figsize=(3, 2))
    axis.plot([1, 2], [2, 4])
    figure.savefig(source / "good.png", facecolor="white")
    figure.savefig(source / "good.jpg", facecolor="white")
    plt.close(figure)
    (source / "broken.png").write_text("not an image")

    images = sorted(source.glob("*.*"))
    sheet, csv, contact = build_candidate_sheet(images, out_dir=tmp_path / "out")
    text = sheet.read_text()
    assert "good.png" in text
    assert "good.jpg" in text
    assert "broken.png" not in text
    assert contact.is_file()
    header = csv.read_text().splitlines()[0]
    assert header.startswith("n,file,pixels")
