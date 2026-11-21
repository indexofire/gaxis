from pathlib import Path

from gaxis.models.schema import describe_data
from gaxis.models.spec import ChartType
from gaxis.spec.infer import infer_spec

DATA = Path(__file__).parent / "data" / "expr.csv"


def test_default_spec_skips_id_columns_and_groups_by_second_factor() -> None:
    spec = infer_spec(describe_data(DATA))
    assert spec.x == "genotype"
    assert spec.y == "expr_fpkm"
    assert spec.hue == "condition"
    assert spec.chart_type is ChartType.bar
    assert spec.xlabel == "genotype"
    assert spec.ylabel == "expr fpkm"


def test_high_cardinality_x_becomes_boxplot() -> None:
    schema = describe_data(DATA)
    spec = infer_spec(schema, x="sample", y="expr_fpkm", hue=None)
    assert spec.chart_type is ChartType.box


def test_numeric_x_becomes_scatter() -> None:
    schema = describe_data(DATA)
    spec = infer_spec(schema, x="od600", y="expr_fpkm", hue="genotype")
    assert spec.chart_type is ChartType.scatter


def test_explicit_choices_win() -> None:
    schema = describe_data(DATA)
    spec = infer_spec(schema, chart_type=ChartType.line, x="time_h", y="od600", hue="genotype")
    assert spec.chart_type is ChartType.line
    assert spec.x == "time_h"
