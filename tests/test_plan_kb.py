"""plan_chart_from_brief uses the knowledge base when it is available."""

from __future__ import annotations

from pathlib import Path

from gaxis.config import load_config
from gaxis.kb.gbrain import GbrainCLI
from gaxis.kb.ingest import KbIngestor
from gaxis.models.tools import PlanChartRequest
from gaxis.service import plan_chart
from gaxis.spec.brief import build_plan

from .manifest_factory import make_manifest


def test_plan_attaches_kb_cases_and_raises_confidence(fake_kb: Path, tmp_path: Path) -> None:
    kb = GbrainCLI(load_config().knowledge)
    KbIngestor(kb, state_path=tmp_path / "data" / "kb" / "state.json").ingest(
        [make_manifest(level="L1")]
    )
    brief = "line chart of rarefaction curves with error bars"
    baseline = build_plan(brief)
    result = plan_chart(PlanChartRequest(brief=brief))
    assert result.degraded is False
    assert result.matches
    assert result.plan.candidate_asset_ids
    assert result.plan.confidence >= baseline.confidence
    assert "knowledge-base case" in result.message


def test_plan_stays_useful_without_a_brain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAXIS_GBRAIN_BIN", str(tmp_path / "missing-gbrain"))
    monkeypatch.setenv("GAXIS_DATA_DIR", str(tmp_path / "data"))
    result = plan_chart(PlanChartRequest(brief="bar chart for mBio"))
    assert result.plan.spec.preset == "asm"
    assert result.matches == []
    assert result.degraded is True


def test_disabled_knowledge_base_is_not_probed(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "gaxis.toml"
    config.write_text("[knowledge]\nenabled = false\n")
    monkeypatch.setenv("GAXIS_CONFIG", str(config))
    result = plan_chart(PlanChartRequest(brief="heatmap of gene expression"))
    assert result.degraded is True
    assert "disabled" in result.message
