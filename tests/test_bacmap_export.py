"""Reference bacmap -> gaxis export converts a results run into table inputs."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "integrations" / "bacmap_export.py"


def _load():
    spec = importlib.util.spec_from_file_location("bacmap_export", SCRIPT)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_reads_amrfinder_and_summary(tmp_path: Path) -> None:
    run = tmp_path / "run"
    sample = run / "26SAL0001"
    (sample / "amr").mkdir(parents=True)
    (sample / "amr" / "amrfinderplus.tsv").write_text(
        "Element symbol\tClass\tType\n"
        "blaCTX-M-14\tBETA-LACTAM\tAMR\n"
        "tet(A)\tTETRACYCLINE\tAMR\n"
        "NA\tNA\tNA\n",
        encoding="utf-8",
    )
    (sample / "report").mkdir()
    (sample / "report" / "26SAL0001_summary.json").write_text(
        json.dumps(
            {
                "sample": "26SAL0001",
                "steps": {
                    "species": {"species": "Salmonella"},
                    "serotype": {"value": "Typhimurium"},
                },
            }
        ),
        encoding="utf-8",
    )
    module = _load()
    manifest = module.export(run, tmp_path / "out")
    assert manifest["samples"] == 1
    assert manifest["amr_rows"] == 2
    long_table = Path(manifest["outputs"]["amr_long"]).read_text(encoding="utf-8")
    assert "26SAL0001,blaCTX-M-14,BETA-LACTAM" in long_table
    metadata = Path(manifest["outputs"]["metadata"]).read_text(encoding="utf-8")
    assert "26SAL0001,Salmonella,Typhimurium" in metadata
