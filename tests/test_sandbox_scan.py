"""Static scan and dependency hints (the gate before anything runs)."""

from pathlib import Path

from gaxis.sandbox.scan import dependency_hints, scan_code


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "figure.py"
    path.write_text(text)
    return path


def test_shell_and_exec_are_blocking(tmp_path: Path) -> None:
    report = scan_code(_write(tmp_path, "import os\nos.system('curl evil')\nexec('1+1')\n"))
    assert report.blocking is True
    codes = {finding.code for finding in report.findings}
    assert {"shell_exec", "eval_exec"} <= codes


def test_network_use_is_a_warning_not_a_block(tmp_path: Path) -> None:
    report = scan_code(_write(tmp_path, "import requests\nrequests.get('http://x')\n"))
    assert report.blocking is False
    assert any(
        finding.code == "network" and finding.severity == "warning" for finding in report.findings
    )


def test_comments_are_ignored(tmp_path: Path) -> None:
    report = scan_code(_write(tmp_path, "# os.system('documented example')\nprint('ok')\n"))
    assert report.blocking is False


def test_copyleft_licence_is_detected(tmp_path: Path) -> None:
    report = scan_code(
        _write(tmp_path, '"""Licensed under the GNU General Public License v3."""\n')
    )
    assert report.copyleft is True
    assert "GPL" in report.licences


def test_dependency_hints_exclude_stdlib(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import os\n"
        "import numpy as np\n"
        "from matplotlib import pyplot as plt\n"
        "import pandas.core.frame\n",
    )
    hints = dependency_hints(path)
    assert hints == ["matplotlib", "numpy", "pandas"]
