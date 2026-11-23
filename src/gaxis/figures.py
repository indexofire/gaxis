"""Figure recipe registry (data in ``style/figure_recipes.toml``)."""

from __future__ import annotations

import tomllib
from importlib import resources

from .models.recipe import FigureRecipe, PanelSpec


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
                chart_type=entry.get("chart_type"),
                x=entry.get("x"),
                y=entry.get("y"),
                hue=entry.get("hue"),
                weight=entry.get("weight"),
                annotations=list(entry.get("annotations", [])),
                preset=entry.get("preset", "default"),
                rotate_labels=int(entry.get("rotate_labels", 0)),
                analysis_recipe=entry.get("analysis"),
                analysis_output=entry.get("analysis_output"),
                analysis_params=dict(entry.get("analysis_params", {})),
                required_columns=list(entry.get("required", [])),
                optional_columns=list(entry.get("optional", [])),
                kind=entry.get("kind", "figure"),
                panels=[
                    PanelSpec(
                        recipe_id=panel["recipe"],
                        label=panel.get("label", ""),
                        input_key=panel.get("input_key"),
                    )
                    for panel in entry.get("panels", [])
                ],
                layout=entry.get("layout"),
            )
        )
    return recipes
