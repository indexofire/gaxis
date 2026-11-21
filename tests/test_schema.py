from pathlib import Path

import pytest

from gaxis.models.schema import ColumnKind, describe_data

DATA = Path(__file__).parent / "data" / "expr.csv"


def test_column_kinds_and_counts() -> None:
    schema = describe_data(DATA)
    assert schema.n_rows == 48
    kinds = {c.name: c.kind for c in schema.columns}
    assert kinds["genotype"] is ColumnKind.categorical
    assert kinds["condition"] is ColumnKind.categorical
    assert kinds["expr_fpkm"] is ColumnKind.numeric
    assert schema.numeric_columns == ["expr_fpkm", "od600", "time_h"]
    assert schema.categorical_columns == ["sample", "genotype", "condition"]


def test_unit_hint_and_markdown_summary() -> None:
    schema = describe_data(DATA)
    profile = schema.column("expr_fpkm")
    assert profile is not None
    assert profile.unit_hint == "FPKM"
    assert "48 rows" in schema.summary_markdown()


def test_tsv_detection_and_missing_ratio(tmp_path: Path) -> None:
    path = tmp_path / "m.tsv"
    path.write_text("a\tb\n1\tx\n\tx\n3\ty\n")
    schema = describe_data(path)
    assert schema.delimiter == "\t"
    profile = schema.column("a")
    assert profile is not None
    assert profile.missing_ratio == pytest.approx(1 / 3, abs=1e-3)


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        describe_data("/nonexistent/none.csv")
