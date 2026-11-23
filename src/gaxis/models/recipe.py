"""Figure recipes: data-driven bindings from a table to a ChartSpec."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .lint import LintReport
from .manifest import OutputFile
from .spec import ChartType


class FigureRecipe(BaseModel):
    recipe_id: str
    title: str
    description: str = ""
    chart_type: ChartType
    x: str | None = None
    y: str | None = None
    hue: str | None = None
    weight: str | None = None
    annotations: list[str] = Field(default_factory=list)
    preset: str = "default"
    rotate_labels: int = 0
    analysis_recipe: str | None = None
    analysis_output: str | None = None
    analysis_params: dict[str, Any] = Field(default_factory=dict)
    required_columns: list[str] = Field(default_factory=list)
    optional_columns: list[str] = Field(default_factory=list)


class ListFigureRecipesRequest(BaseModel):
    chart_type: ChartType | None = None


class ListFigureRecipesResult(BaseModel):
    recipes: list[FigureRecipe] = Field(default_factory=list)
    total: int = 0


class RenderFigureRecipeRequest(BaseModel):
    recipe_id: str
    data_path: str
    preset: str | None = None
    out_dir: str | None = None
    color_map: dict[str, str] = Field(default_factory=dict)
    run_analysis: bool = False
    analysis_params: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class RenderFigureRecipeResult(BaseModel):
    recipe_id: str
    figure_id: str
    code_path: str = ""
    outputs: list[OutputFile] = Field(default_factory=list)
    lint: LintReport = Field(default_factory=LintReport)
    manifest: dict[str, Any] = Field(default_factory=dict)
    source: Literal["figure_recipe"] = "figure_recipe"
    analysis_run_id: str | None = None
    not_implemented: bool = False
