"""Brief -> ChartPlan: the entry point of service flow 1 (no data required)."""

from gaxis.models.spec import ChartType
from gaxis.spec.brief import build_plan, parse_preset_hint


def test_grouped_bar_brief_captures_journal_style_and_language() -> None:
    plan = build_plan(
        "grouped bar chart with error bars for a Nature Microbiology submission in ggplot2"
    )
    assert plan.spec.chart_type is ChartType.bar
    assert plan.spec.preset == "nature_microbiology"
    assert plan.spec.backend == "r"
    assert {c.role for c in plan.required_columns} == {"x", "y", "hue"}
    assert any("error bars" in note for note in plan.style_notes)
    assert 0.4 <= plan.confidence <= 0.9


def test_chinese_brief_is_understood() -> None:
    plan = build_plan("画分组柱状图，带误差棒，色盲友好，投 mBio")
    assert plan.spec.chart_type is ChartType.bar
    assert plan.spec.preset == "asm"
    assert plan.spec.palette == "okabe_ito"
    assert any("error bars" in note for note in plan.style_notes)


def test_stacked_bar_wins_over_plain_bar() -> None:
    plan = build_plan("stacked bar chart of community composition")
    assert plan.spec.chart_type is ChartType.stacked_bar


def test_vague_brief_asks_the_right_questions() -> None:
    plan = build_plan("make it look good")
    assert plan.spec.chart_type is ChartType.bar  # documented fallback
    assert any("Which chart type" in question for question in plan.open_questions)
    assert any("journal" in question for question in plan.open_questions)
    assert plan.confidence < 0.5


def test_heatmap_roles_are_categorical_by_categorical_value() -> None:
    plan = build_plan("heatmap of gene expression by condition")
    roles = {column.role: column.kind for column in plan.required_columns}
    assert plan.spec.chart_type is ChartType.heatmap
    assert roles["x"] == "categorical"
    assert roles["y"] == "numeric"


def test_panels_are_flagged_not_silently_dropped() -> None:
    plan = build_plan("multi-panel figure A/B/C with line charts")
    assert any("multi-panel" in note for note in plan.style_notes)
    assert any("Panel layout" in question for question in plan.open_questions)


def test_preset_hint_is_exposed_on_its_own() -> None:
    assert parse_preset_hint("for an ISME Journal submission") == "isme"
    assert parse_preset_hint("something generic") is None


def test_confirmation_policy_is_configurable(monkeypatch) -> None:
    from gaxis.models.tools import PlanChartRequest
    from gaxis.service import plan_chart

    brief = "grouped bar chart with error bars, Nature Microbiology, ggplot2"

    monkeypatch.setenv("GAXIS_CONFIRM_MODE", "never")
    assert plan_chart(PlanChartRequest(brief=brief)).requires_confirmation is False

    monkeypatch.setenv("GAXIS_CONFIRM_MODE", "always")
    assert plan_chart(PlanChartRequest(brief=brief)).requires_confirmation is True

    monkeypatch.delenv("GAXIS_CONFIRM_MODE")
    monkeypatch.setenv("GAXIS_CONFIRM_MIN_CONFIDENCE", "0.99")
    result = plan_chart(PlanChartRequest(brief=brief))
    assert result.requires_confirmation is True
    assert result.confirmation_threshold == 0.99
