"""Figure recipe registry (data in ``style/figure_recipes.toml``)."""

from __future__ import annotations

import tomllib
from importlib import resources

from .models.recipe import FigureRecipe


def load_figure_recipes() -> list[FigureRecipe]:
    path = resources.files("gaxis.style").joinpath("figure_recipes.toml")
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    recipes: list[FigureRecipe] = []
    for entry in payload.get("recipe", []):
        recipes.append(
            FigureRecipe(
                recipe_id=entry["id"],
                title=entry["title"],
                description=entry.get("description", ""),
                chart_type=entry["chart_type"],
                x=entry.get("x"),
                y=entry.get("y"),
                hue=entry.get("hue"),
                weight=entry.get("weight"),
                annotations=list(entry.get("annotations", [])),
                preset=entry.get("preset", "default"),
                required_columns=list(entry.get("required", [])),
                optional_columns=list(entry.get("optional", [])),
            )
        )
    return recipes
