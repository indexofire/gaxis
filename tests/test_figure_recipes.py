"""Figure recipes: curated table -> figure contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaxis.errors import GaxisError
from gaxis.models.recipe import ListFigureRecipesRequest, RenderFigureRecipeRequest
from gaxis.service import figure_recipes, render_figure_recipe

DATA = Path(__file__).parent / "data" / "amr_edges.csv"


def test_recipes_are_listed_and_filterable() -> None:
    result = figure_recipes()
    ids = {recipe.recipe_id for recipe in result.recipes}
    assert {"amr-network", "amr-prevalence-bar", "snp-tree"} <= ids
    networks = figure_recipes(ListFigureRecipesRequest(chart_type="network"))
    assert [recipe.recipe_id for recipe in networks.recipes] == ["amr-network"]


def test_render_amr_network_recipe(tmp_path: Path) -> None:
    result = render_figure_recipe(
        RenderFigureRecipeRequest(
            recipe_id="amr-network",
            data_path=str(DATA),
            out_dir=str(tmp_path / "figures"),
        )
    )
    assert result.recipe_id == "amr-network"
    assert result.lint.ok, result.lint.format_text()
    assert result.outputs
    assert result.manifest["recipe_id"] == "amr-network"
    assert result.manifest["source"] == "figure_recipe"
    code = Path(result.code_path).read_text(encoding="utf-8")
    assert "import gaxis" not in code


def test_recipe_contract_violation_is_explicit(tmp_path: Path) -> None:
    table = tmp_path / "wrong.csv"
    table.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(GaxisError) as excinfo:
        render_figure_recipe(
            RenderFigureRecipeRequest(recipe_id="amr-network", data_path=str(table))
        )
    assert excinfo.value.code == "recipe_contract_violation"
    assert "source" in excinfo.value.message


def test_dry_run_does_not_execute(tmp_path: Path) -> None:
    result = render_figure_recipe(
        RenderFigureRecipeRequest(
            recipe_id="amr-network",
            data_path=str(DATA),
            out_dir=str(tmp_path / "dry"),
            dry_run=True,
        )
    )
    assert result.outputs == []
    assert Path(result.code_path).is_file()


def test_recipe_render_honours_rotate_labels(tmp_path: Path) -> None:
    nodes = tmp_path / "nodes.csv"
    nodes.write_text(
        "gene,prevalence,gene_class,very_long_gene_name\n"
        "blaCTX-M-14,0.5,BETA-LACTAM,x\n"
        "blaTEM-1,0.4,BETA-LACTAM,x\n",
        encoding="utf-8",
    )
    result = render_figure_recipe(
        RenderFigureRecipeRequest(
            recipe_id="amr-prevalence-bar",
            data_path=str(nodes),
            out_dir=str(tmp_path / "rotated"),
            dry_run=True,
        )
    )
    code = Path(result.code_path).read_text(encoding="utf-8")
    assert "'rotate_labels': 90" in code or '"rotate_labels": 90' in code
