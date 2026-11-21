"""Crop-quality heuristics: figure vs body text vs blank vs tinted vs clipped."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from gaxis.quality_image import analyse_crop, crop_clean_score


def _image(path: Path, *, bars: bool = True) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(4, 2.6), dpi=140)
    if bars:
        axis.bar(["A", "B", "C"], [3, 7, 5], color="#0072B2")
    figure.savefig(path, facecolor="white")
    plt.close(figure)
    return path


def test_clean_figure_scores_high(tmp_path: Path) -> None:
    report = analyse_crop(_image(tmp_path / "figure.png"))
    assert report.score >= 0.75, report.as_dict()
    assert report.verdict in {"ok", "tinted"}
    assert "text" not in report.verdict


def test_thin_stroke_figure_is_not_mistaken_for_text(tmp_path: Path) -> None:
    """A phylogenetic tree is thin strokes with labels — still a figure, not body text."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = tmp_path / "tree.png"
    figure, axis = plt.subplots(figsize=(4, 3), dpi=140)
    for step in range(30):
        axis.plot([0, 0.5, 1], [step / 30, 0.5, (step * 7 % 30) / 30], linewidth=0.5)
    axis.axis("off")
    figure.savefig(path, facecolor="white")
    plt.close(figure)
    report = analyse_crop(path)
    assert "text" not in report.verdict, report.as_dict()


def test_line_and_scatter_are_not_mistaken_for_text(tmp_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for kind in ("line", "scatter"):
        path = tmp_path / f"{kind}.png"
        figure, axis = plt.subplots(figsize=(4, 2.6), dpi=140)
        if kind == "line":
            axis.plot([1, 2, 3, 4], [2, 5, 3, 6])
        else:
            axis.scatter([1, 2, 3, 4], [2, 5, 3, 6])
        figure.savefig(path, facecolor="white")
        plt.close(figure)
        report = analyse_crop(path)
        assert report.verdict != "text", (kind, report.as_dict())
        assert report.score >= 0.75


def test_blank_crop_scores_zero(tmp_path: Path) -> None:
    from PIL import Image

    blank = tmp_path / "blank.png"
    Image.new("RGB", (400, 300), "white").save(blank)
    assert crop_clean_score(blank) == 0.0
    assert analyse_crop(blank).verdict == "blank"


def test_body_text_crop_is_penalised(tmp_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    page = tmp_path / "text.png"
    figure = plt.figure(figsize=(6, 4), dpi=120)
    for row in range(18):
        figure.text(
            0.05,
            0.95 - row * 0.05,
            "the quick brown fox jumps over the lazy dog " * 2,
            fontsize=8,
        )
    figure.savefig(page, facecolor="white")
    plt.close(figure)
    report = analyse_crop(page)
    assert report.line_bands >= 6
    assert report.band_height_cv < 0.2
    assert report.score < 0.6, report.as_dict()
    assert "text" in report.verdict


def test_dense_artwork_on_a_tinted_background_is_not_penalised(tmp_path: Path) -> None:
    """Gel photos and heatmaps legitimately have a coloured background."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tinted = tmp_path / "tinted.png"
    figure, axis = plt.subplots(figsize=(4, 2.6), dpi=140, facecolor="#f2e394")
    axis.bar(["A", "B"], [1, 2])
    figure.savefig(tinted, facecolor="#f2e394")
    plt.close(figure)
    report = analyse_crop(tinted)
    assert report.tint_ratio > 0.35
    assert report.ink_ratio > 0.1
    assert report.score >= 0.75


def test_sparse_ink_on_a_tinted_field_is_flagged(tmp_path: Path) -> None:
    """A scanned page: light coloured paper with a little text on it."""
    from PIL import Image, ImageDraw

    page = tmp_path / "scan.png"
    image = Image.new("RGB", (500, 700), "#f2e394")
    draw = ImageDraw.Draw(image)
    for row in range(6):
        draw.text((30, 40 + row * 40), "sparse scanned text", fill="black")
    image.save(page)
    report = analyse_crop(page)
    assert report.tint_ratio > 0.35
    assert report.ink_ratio < 0.1
    assert report.score <= 0.85


def test_accepts_bytes_as_well_as_paths(tmp_path: Path) -> None:
    image = _image(tmp_path / "figure.png")
    assert crop_clean_score(image.read_bytes()) == crop_clean_score(image)
