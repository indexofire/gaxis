"""Scanning a repository for plotting code (no git, no network)."""

from __future__ import annotations

from pathlib import Path

from gaxis.acquire.repo import (
    RepoLink,
    find_license,
    inventory_repository,
    scan_scripts,
)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "analysis").mkdir(parents=True)
    (repo / "LICENSE").write_text("MIT License\n\nPermission is hereby granted...")
    (repo / "LICENSE_PLACEHOLDER").unlink(missing_ok=True)
    (repo / "plot_figure1.py").write_text(
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot([1, 2], [3, 4])\n"
        "fig.savefig('figure1.pdf')\n"
    )
    (repo / "figure2.R").write_text(
        "library(ggplot2)\np <- ggplot(df, aes(x, y)) + geom_point()\nggsave('figure2.pdf', p)\n"
    )
    (repo / "analysis" / "stats.py").write_text(
        "import pandas as pd\nprint(pd.DataFrame({'a': [1]}).mean())\n"
    )
    (repo / "README.md").write_text("Repository for the paper.\n")
    return repo


def test_plotting_scripts_are_ranked_above_analysis_code(tmp_path: Path) -> None:
    scripts = scan_scripts(_repo(tmp_path))
    names = [script.relative_path for script in scripts]
    assert "plot_figure1.py" in names
    assert "figure2.R" in names
    assert "analysis/stats.py" not in names
    languages = {script.language for script in scripts}
    assert languages == {"python", "r"}


def test_savefig_and_ggsave_raise_the_score(tmp_path: Path) -> None:
    scripts = {script.relative_path: script for script in scan_scripts(_repo(tmp_path))}
    assert scripts["plot_figure1.py"].score >= 0.6
    assert "savefig" in scripts["plot_figure1.py"].markers


def test_licence_detection(tmp_path: Path) -> None:
    assert find_license(_repo(tmp_path)) == "MIT"


def test_inventory_reports_licence_and_scripts(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    link = RepoLink(url="https://github.com/lab/figs", host="github", owner="lab", repo="figs")
    inventory = inventory_repository(link, repo)
    assert inventory.license == "MIT"
    assert inventory.scripts
    assert inventory.local_path == repo


def test_scripts_outside_the_repo_are_ignored(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "plot_supp.py").write_text("import matplotlib\nplt.savefig('x.pdf')\n")
    names = {script.relative_path for script in scan_scripts(repo)}
    assert "docs/plot_supp.py" not in names
