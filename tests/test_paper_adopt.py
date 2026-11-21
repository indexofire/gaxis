"""Adopting a reproduced paper script as an adaptable template."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gaxis.errors import GaxisError
from gaxis.kb.adopt import adopt_asset, rewrite_path_interface
from gaxis.models.paper import CodeCandidate
from gaxis.models.spec import ChartType
from gaxis.models.tools import AdaptChartCodeRequest
from gaxis.service import adapt_chart_code, knowledge

from .manifest_factory import make_manifest

SCRIPT = '''"""Paper figure 1: bar chart of counts."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

DATA_PATH = Path("unused.csv")

rows = list(csv.DictReader(DATA_PATH.open(newline="", encoding="utf-8")))
figure, axis = plt.subplots(figsize=(3.2, 2.4))
axis.bar([row["g"] for row in rows], [float(row["v"]) for row in rows])
axis.set_xlabel("group")
axis.set_ylabel("value")
figure.savefig("paper-figure.pdf")
'''


def _data_root() -> Path:
    return Path(os.environ["GAXIS_DATA_DIR"])


def _script(tmp_path: Path, text: str = SCRIPT) -> Path:
    path = tmp_path / "paper_figure.py"
    path.write_text(text, encoding="utf-8")
    return path


def test_adopt_requires_a_declared_input_interface(fake_kb: Path, tmp_path: Path) -> None:
    kb = knowledge()
    assert kb is not None
    manifest = make_manifest(level="L2", chart_type=ChartType.bar)
    broken = _script(tmp_path, "print('no interface')\n")
    with pytest.raises(GaxisError) as excinfo:
        adopt_asset(kb, manifest=manifest, data_root=_data_root(), code=broken)
    assert excinfo.value.code == "adoption_refused"
    assert "DATA_PATH" in excinfo.value.message


def test_adopt_then_adapt_runs_paper_code(fake_kb: Path, tmp_path: Path) -> None:
    kb = knowledge()
    assert kb is not None
    manifest = make_manifest(level="L2", chart_type=ChartType.bar)
    script = _script(tmp_path)
    manifest.code_candidates = [CodeCandidate(code_path=str(script), license="MIT")]
    adopted = adopt_asset(kb, manifest=manifest, data_root=_data_root(), code=script, preset="asm")
    assert adopted.interface == "path"
    assert adopted.backend == "python"
    page = kb.get_page(adopted.slug)
    assert page is not None
    assert page["frontmatter"]["origin"] == "paper"
    assert page["frontmatter"]["interface"] == "path"

    data = _data_root() / "groups.csv"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("g,v\nWT,4\ndpsA,7\nrpoS,9\n", encoding="utf-8")
    result = adapt_chart_code(
        AdaptChartCodeRequest(
            data_path=str(data), asset_id=adopted.slug, preset="asm", formats=["pdf"]
        )
    )
    assert result.source == "kb_asset"
    assert result.asset_ids == [adopted.slug]
    assert any(output.format == "pdf" for output in result.outputs)
    code = Path(result.code_path).read_text(encoding="utf-8")
    assert str(data) in code
    assert "figure.savefig" in code


def test_rewrite_path_interface_is_verified() -> None:
    with pytest.raises(GaxisError) as excinfo:
        rewrite_path_interface("print('x')\n", backend="python", data_path=Path("/x.csv"))
    assert excinfo.value.code == "adaptation_failed"

    adapted = rewrite_path_interface(
        "DATA_PATH = Path('old.csv')\nOUT_DIR = Path('old')\nplot()\n",
        backend="python",
        data_path=Path("/data/new.csv"),
        out_dir=Path("/out"),
    )
    assert "DATA_PATH = Path('/data/new.csv')" in adapted
    assert "OUT_DIR = Path('/out')" in adapted
    assert "plot()" in adapted
