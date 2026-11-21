"""KB template seeding and script adaptation (no network, fake brain)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gaxis.adapt import adapt_script
from gaxis.errors import GaxisError
from gaxis.kb.templates import seed_templates
from gaxis.models.spec import ChartSpec
from gaxis.models.tools import AdaptChartCodeRequest
from gaxis.service import adapt_chart_code, knowledge


def _data_root() -> Path:
    return Path(os.environ["GAXIS_DATA_DIR"])


def test_seed_is_idempotent_and_pages_carry_code(fake_kb: Path) -> None:
    kb = knowledge()
    assert kb is not None
    first = seed_templates(
        kb, data_root=_data_root(), presets=["nature_microbiology"], backends=("python",)
    )
    assert len(first.written) == 6
    assert not first.failed
    assert len(first.written) == 6
    second = seed_templates(
        kb, data_root=_data_root(), presets=["nature_microbiology"], backends=("python",)
    )
    assert not second.written
    assert len(second.skipped) == 6
    page = kb.get_page("template:nature_microbiology-bar-python")
    assert page is not None
    assert page["frontmatter"]["code_sha256"]
    assert "def summarise(" in page["compiled_truth"]


def test_adapt_retrieves_verified_template_and_rebinds_columns(fake_kb: Path) -> None:
    kb = knowledge()
    assert kb is not None
    seed_templates(
        kb, data_root=_data_root(), presets=["nature_microbiology"], backends=("python",)
    )
    data = _data_root() / "renamed.csv"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text(
        "strain,group,value\nWT,LB,10\nWT,M9,12\nmut,LB,7\nmut,M9,9\n", encoding="utf-8"
    )
    result = adapt_chart_code(
        AdaptChartCodeRequest(
            data_path=str(data),
            query="bar chart",
            preset="nature_microbiology",
            formats=["pdf"],
        )
    )
    assert result.source == "kb_asset"
    assert result.asset_ids == ["template:nature_microbiology-bar-python"]
    assert result.fallback_reason == ""
    assert result.not_implemented is False
    code = Path(result.code_path).read_text(encoding="utf-8")
    assert "'strain'" in code
    assert "'group'" in code
    assert result.lint.ok, result.lint.format_text()


def test_missing_preset_falls_back_with_reason(fake_kb: Path) -> None:
    data = _data_root() / "small.csv"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("g,v\nA,1\nB,2\nA,3\n", encoding="utf-8")
    result = adapt_chart_code(
        AdaptChartCodeRequest(data_path=str(data), preset="asm", formats=["pdf"])
    )
    assert result.source == "builtin_templates"
    assert "gaxis kb seed" in result.fallback_reason
    assert result.lint.ok, result.lint.format_text()


def test_paper_asset_is_not_adapted_silently(fake_kb: Path) -> None:
    kb = knowledge()
    assert kb is not None
    kb.put_page(
        "paper-kb:some-fig",
        "---\ntype: analysis\ntitle: Fig 1\n---\n\n# Fig 1\n\nbar chart\n",
    )
    data = _data_root() / "small.csv"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("g,v\nA,1\nB,2\n", encoding="utf-8")
    result = adapt_chart_code(
        AdaptChartCodeRequest(data_path=str(data), asset_id="paper-kb:some-fig", formats=["pdf"])
    )
    assert result.source == "builtin_templates"
    assert "paper figure, not a template" in result.fallback_reason


def test_adapt_script_refuses_unexpected_template(tmp_path: Path) -> None:
    spec = ChartSpec(chart_type="bar", x="a", y="b")
    with pytest.raises(GaxisError) as excinfo:
        adapt_script(
            "print('hello')\n",
            backend="python",
            spec=spec,
            data_path=tmp_path / "x.csv",
            out_dir=tmp_path / "out",
            stem="x",
            delimiter=",",
        )
    assert excinfo.value.code == "adaptation_failed"


def test_adapt_script_handles_r_templates() -> None:
    template = (
        "DATA_PATH <- 'old.csv'\n"
        "OUT_DIR <- 'old'\n"
        "STEM <- 'old'\n"
        'SEP <- ","\n'
        "SPEC <- list(\n"
        "  x = 'a',\n"
        "  y = 'b',\n"
        '  formats = c("pdf", "png")\n'
        ")\n"
        "ggplot()\n"
    )
    spec = ChartSpec(chart_type="bar", x="strain", y="value", backend="r")
    adapted, applied = adapt_script(
        template,
        backend="r",
        spec=spec,
        data_path=Path("/data/x.tsv"),
        out_dir=Path("/out/x"),
        stem="x",
        delimiter="\t",
    )
    assert "data path" in applied
    assert 'DATA_PATH <- "/data/x.tsv"' in adapted
    assert 'SEP <- "\\t"' in adapted
    assert 'x = "strain"' in adapted
    assert adapted.count("\n)") >= 1
    assert 'formats = c("pdf", "png")' in adapted
    assert "ggplot()" in adapted
