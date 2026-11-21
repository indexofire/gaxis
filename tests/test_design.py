"""Design quality: aesthetics + information design, explained by features."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from gaxis.design import analyse_design

GOOD_CAPTION = (
    "Fig. 1 | Growth rate of four isolates in M9 minimal medium. "
    "Bars are means of n = 12 replicates and error bars are s.d.; "
    "the colour-blind-safe palette is unchanged across panels a-d."
)


def _figure(path: Path, *, style: str) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(3.5, 2.3), dpi=200)
    if style == "publication":
        palette = ["#0072B2", "#E69F00", "#009E73", "#CC79A7"]
        for index, (label, values) in enumerate(
            {"WT": [1, 2, 3], "dpsA": [4, 5, 6], "rpoS": [2, 3, 4], "hfq": [3, 2, 5]}.items()
        ):
            axis.plot([0, 6, 12], values, marker="o", color=palette[index], label=label)
        axis.set_xlabel("time (h)")
        axis.set_ylabel("growth rate (h$^{-1}$)")
        axis.legend(frameon=False, fontsize=7)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(False)
    else:
        # chart junk: rainbow palette, heavy grid, tiny unlabeled everything
        axis.grid(True, which="both", linewidth=1.0)
        for step in range(12):
            axis.plot([0, 6, 12], [step, 12 - step, step / 2], color=plt.cm.jet(step / 12))
        axis.set_xticks([])
        axis.set_yticks([])
    figure.savefig(path, facecolor="white")
    plt.close(figure)
    return path


def test_objective_half_separates_complete_from_bare_figures(tmp_path: Path) -> None:
    good = analyse_design(
        _figure(tmp_path / "good.png", style="publication"),
        caption=GOOD_CAPTION,
        label_font_pt=7.0,
    )
    bad = analyse_design(
        _figure(tmp_path / "bad.png", style="junk"), caption="Fig. 2 | results", label_font_pt=4.0
    )
    assert good.visualization > bad.visualization
    assert good.visualization > 0.8
    assert bad.visualization < 0.6
    # aesthetics is not measured from pixels: it must stay unjudged
    assert good.aesthetic is None
    assert bad.aesthetic is None
    assert good.method == "objective"


def test_caption_signals_are_detected() -> None:
    from gaxis.design import _caption_signals

    signals = _caption_signals(GOOD_CAPTION, 7.0)
    assert "units" in signals["signals"]
    assert "uncertainty" in signals["signals"]
    assert "sample_size" in signals["signals"]
    assert "colourblind" in signals["signals"]
    assert signals["has_panels"] is True

    bare = _caption_signals("Fig. 3 | Something happened.", 6.0)
    assert bare["has_units"] is False
    assert bare["has_uncertainty"] is False


def test_photo_like_content_is_not_a_chart(tmp_path: Path) -> None:
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(0)
    noise = (rng.random((400, 500, 3)) * 255).astype("uint8")
    path = tmp_path / "photo.png"
    Image.fromarray(noise).save(path)
    report = analyse_design(path, caption="micrograph of biofilm", label_font_pt=None)
    assert report.features.photo_like is True
    assert report.features.chart_like is False
    assert report.visualization < 0.5
    assert any("photographic" in note for note in report.notes)


def test_colour_blind_safety_is_measured(tmp_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    safe = tmp_path / "safe.png"
    figure, axis = plt.subplots(figsize=(3, 2), dpi=150)
    for index, colour in enumerate(["#0072B2", "#E69F00", "#009E73"]):
        axis.bar([index], [index + 1], color=colour)
    figure.savefig(safe, facecolor="white")
    plt.close(figure)
    report = analyse_design(safe, caption="bars", label_font_pt=7)
    assert report.features.colorblind_safe is True

    # red/green is the classic protan/deutan confusion: simulated hues collapse
    unsafe = tmp_path / "unsafe.png"
    figure, axis = plt.subplots(figsize=(3, 2), dpi=150)
    for index, colour in enumerate(["#ff0000", "#00ff00"]):
        axis.bar([index], [index + 1], color=colour)
    figure.savefig(unsafe, facecolor="white")
    plt.close(figure)
    unsafe_report = analyse_design(unsafe, caption="bars", label_font_pt=7)
    assert unsafe_report.features.colorblind_safe is False


def test_scores_are_explainable(tmp_path: Path) -> None:
    report = analyse_design(
        _figure(tmp_path / "good.png", style="publication"),
        caption="Fig. 1 | x",
        label_font_pt=4.2,
    )
    assert any("below the 5 pt" in note for note in report.notes)
    payload = report.model_dump()
    assert payload["model"] == "objective_v1"
    assert payload["aesthetic"] is None
    assert 0.0 <= payload["visualization"] <= 1.0
    assert payload["features"]["palette"]
