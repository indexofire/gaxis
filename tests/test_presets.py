import pytest

from gaxis.models.spec import ChartSpec
from gaxis.style.palettes import PALETTES, get_palette
from gaxis.style.presets import load_preset, preset_names, resolve_size

MICROBIOLOGY_PRESETS = {
    "nature_microbiology",
    "asm",
    "isme",
    "cell_host_microbe",
    "microbial_genomics",
    "default",
}


def test_microbiology_presets_present() -> None:
    assert set(preset_names()) >= MICROBIOLOGY_PRESETS


@pytest.mark.parametrize("name", preset_names())
def test_preset_geometry_is_sane(name: str) -> None:
    preset = load_preset(name)
    assert preset.width_single_mm < preset.width_double_mm
    assert preset.base_font_pt >= 5
    assert preset.label_font_pt >= preset.base_font_pt
    assert preset.dpi >= 300


def test_double_column_width_implies_double_height() -> None:
    preset = load_preset("nature_microbiology")
    width, height = resolve_size(
        ChartSpec(preset=preset.name, width_mm=preset.width_double_mm), preset
    )
    assert width == preset.width_double_mm
    assert height == preset.height_double_mm


def test_rc_params_are_valid_matplotlib_keys() -> None:
    matplotlib = pytest.importorskip("matplotlib")
    from gaxis.style.rc import build_rc

    rc = build_rc(load_preset("nature_microbiology"), width_mm=89, height_mm=60, dpi=600)
    assert [key for key in rc if key not in matplotlib.rcParams] == []
    assert rc["pdf.fonttype"] == 42
    assert get_palette("okabe_ito").colorblind_safe


def test_unknown_palette_is_rejected() -> None:
    with pytest.raises(KeyError):
        get_palette("not-a-palette")
    assert "okabe_ito" in PALETTES
