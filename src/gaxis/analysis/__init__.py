"""Analysis recipes: table -> table steps that feed publication figures.

Algorithms are not implemented here. A recipe wraps an existing method (author code,
a standard library such as vegan/igraph, or a thin, documented computation) and records
its input contract, parameters and provenance. Low-level bioinformatics (assembly,
typing, AMR calling) belongs to bacmap/gmlst/gspec/gside and is never re-run here.
"""

from .amr import RECIPE_AMR, list_recipes, run_amr_cooccurrence

__all__ = ["RECIPE_AMR", "list_recipes", "run_amr_cooccurrence"]
