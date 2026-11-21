"""Reading human ranks back from the sheet, and refusing to clobber them."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaxis.quality import build_sheet, parse_sheet_ranks

from .manifest_factory import make_manifest


def test_parse_ranks_from_a_filled_sheet() -> None:
    markdown = """\
| # | figure | caption | px | vector | cited | crop | score | human rank |
|---|---|---|---|---|---|---|---|---|
| 1 | Fig. 1 (pdf-a/fig-1) | caption | 1000x800 | no | yes | 1.00 | 0.87 | 2 |
| 2 | Fig. 2 (pdf-a/fig-2) | caption | 1000x800 | no | yes | 1.00 | 0.87 | 1 |
| 3 | Fig. 3 (pdf-a/fig-3) | caption | 1000x800 | no | yes | 1.00 | 0.87 | |
"""
    assert parse_sheet_ranks(markdown) == [("pdf-a/fig-1", 2), ("pdf-a/fig-2", 1)]


def test_empty_sheet_has_no_ranks() -> None:
    empty = "| 1 | Fig. 1 (pdf-a/fig-1) | c | - | no | yes | 1.00 | 0.87 | |"
    assert parse_sheet_ranks(empty) == []


def test_regenerating_a_ranked_sheet_is_refused(tmp_path: Path) -> None:
    manifests = [make_manifest()]
    sheet, _ = build_sheet(manifests, data_root=tmp_path, out_dir=tmp_path)
    lines = []
    for line in sheet.read_text().splitlines():
        if line.startswith("| 1 |"):
            cells = line.strip().strip("|").split("|")
            cells[-1] = " 1 "
            line = "|" + "|".join(cells) + "|"
        lines.append(line)
    sheet.write_text("\n".join(lines) + "\n")
    with pytest.raises(FileExistsError, match="human ranks"):
        build_sheet(manifests, data_root=tmp_path, out_dir=tmp_path)
    build_sheet(manifests, data_root=tmp_path, out_dir=tmp_path, force=True)


def test_template_csv_is_written(tmp_path: Path) -> None:
    build_sheet([make_manifest()], data_root=tmp_path, out_dir=tmp_path)
    template = (tmp_path / "rankings.template.csv").read_text().splitlines()
    assert template[0] == "manifest_id,human_rank"
    assert template[1] == "pdf-abc12345/fig-1,"
