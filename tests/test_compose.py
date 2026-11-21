"""Multi-panel composition: vector placement, labels, manifest, layout errors."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("matplotlib")

from gaxis.errors import GaxisError
from gaxis.models.tools import RenderRequest
from gaxis.service import compose, render

DATA = Path(__file__).parent / "data" / "expr.csv"


@pytest.fixture(autouse=True)
def _isolated_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path / "data"))


def _panel(tmp_path: Path, chart: str, x: str, y: str) -> str:
    result = render(
        RenderRequest(
            data_path=str(DATA),
            chart_type=chart,  # type: ignore[arg-type]
            x=x,
            y=y,
            formats=["pdf"],
            preset="nature_microbiology",
        )
    )
    return result.figure_id


def test_compose_two_panels_keeps_vector_and_labels(tmp_path: Path) -> None:
    first = _panel(tmp_path, "bar", "genotype", "expr_fpkm")
    second = _panel(tmp_path, "line", "time_h", "od600")
    manifest = compose([first, second], preset="nature_microbiology", out_dir=tmp_path / "comp")
    pdf = Path(manifest.output_pdf)
    assert pdf.is_file()
    assert pdf.stat().st_size > 5000
    assert manifest.layout == (1, 2)
    assert [panel.label for panel in manifest.panels] == ["A", "B"]
    assert all(panel.code_sha256 for panel in manifest.panels)
    assert manifest.lint.ok, manifest.lint.format_text()

    import fitz

    with fitz.open(pdf) as doc:
        text = doc[0].get_text()
        assert "A" in text
        assert "B" in text
        page = doc[0].rect
        assert page.width == pytest.approx(manifest.width_mm * 72 / 25.4, rel=0.02)


def test_layout_too_small_is_rejected(tmp_path: Path) -> None:
    first = _panel(tmp_path, "bar", "genotype", "expr_fpkm")
    second = _panel(tmp_path, "line", "time_h", "od600")
    with pytest.raises(GaxisError) as excinfo:
        compose([first, second], layout=(1, 1), out_dir=tmp_path / "comp")
    assert excinfo.value.code == "bad_layout"


def test_compose_needs_at_least_two_panels(tmp_path: Path) -> None:
    first = _panel(tmp_path, "bar", "genotype", "expr_fpkm")
    with pytest.raises(GaxisError) as excinfo:
        compose([first], out_dir=tmp_path / "comp")
    assert excinfo.value.code == "insufficient_panels"


def test_unknown_panel_is_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(GaxisError) as excinfo:
        compose(["does-not-exist", "also-missing"], out_dir=tmp_path)
    assert excinfo.value.code == "figure_not_found"


def test_uniform_composition_rerenders_panels_at_cell_size(tmp_path: Path) -> None:
    first = _panel(tmp_path, "bar", "genotype", "expr_fpkm")
    second = _panel(tmp_path, "line", "time_h", "od600")
    manifest = compose(
        [first, second],
        preset="asm",
        out_dir=tmp_path / "comp",
        layout=(1, 2),
        uniform=True,
    )
    assert manifest.uniform is True
    assert manifest.lint.ok, manifest.lint.format_text()
    assert len(manifest.panels) == 2
    for panel in manifest.panels:
        assert panel.code_sha256
        assert Path(panel.source_file).is_file()

    import fitz

    with fitz.open(manifest.output_pdf) as doc:
        assert doc.page_count == 1
