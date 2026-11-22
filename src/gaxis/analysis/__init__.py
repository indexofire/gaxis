"""Analysis recipes: table -> table steps that feed publication figures.

Algorithms are not implemented here. A recipe wraps an existing method (author code,
a standard library such as vegan/igraph, or a thin, documented computation) and records
its input contract, parameters and provenance. Low-level bioinformatics (assembly,
typing, AMR calling) belongs to bacmap/gmlst/gspec/gside and is never re-run here.
"""

from typing import Any

from .amr import RECIPE_AMR, run_amr_cooccurrence
from .tree import RECIPE_TREE, run_newick_to_table
from .workflows import check_workflow, list_workflows, scaffold_snp_tree

__all__ = [
    "RECIPE_AMR",
    "RECIPE_TREE",
    "check_workflow",
    "list_recipes",
    "list_workflows",
    "run_amr_cooccurrence",
    "run_newick_to_table",
    "scaffold_snp_tree",
]


def list_recipes() -> list[dict[str, Any]]:
    """All table -> table recipes (AMR co-occurrence, Newick conversion)."""
    return [RECIPE_AMR, RECIPE_TREE]
