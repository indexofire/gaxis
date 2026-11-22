"""AMR gene co-occurrence network (table -> nodes/edges).

Input contract: one row per observed AMR gene per sample (long format):
``sample,gene[,gene_class]``. Absence is implied. This is a thin, documented
co-occurrence computation (pairwise Jaccard or shared-sample counts), not a
reimplementation of AMR calling: the user's genes come from bacmap/ABRicate.

Output: ``nodes.csv`` (gene, samples, prevalence, gene_class) and ``edges.csv``
(source, target, weight, support, jaccard), ready for ``gaxis render --chart network``.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import __version__
from ..errors import GaxisError
from ..models.analysis import AmrCooccurrenceParams, AnalysisRun

RECIPE_AMR = {
    "id": "amr-cooccurrence",
    "title": "AMR gene co-occurrence network",
    "input": "long table: sample,gene[,gene_class]",
    "outputs": ["nodes.csv", "edges.csv"],
    "params": ["min_prevalence", "min_support", "weight"],
    "engine": "python (stdlib only)",
    "note": "consumes gene calls from bacmap/ABRicate; does not run AMR calling",
}

SAMPLE_ALIASES = ("sample", "sample_id", "genome", "isolate", "strain")
GENE_ALIASES = ("gene", "amr_gene", "feature", "determinant")
CLASS_ALIASES = ("gene_class", "class", "category", "resistance_class")


def list_recipes() -> list[dict[str, Any]]:
    return [RECIPE_AMR]


@dataclass
class _Row:
    sample: str
    gene: str
    gene_class: str


def _delimiter(path: Path) -> str:
    return "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","


def _pick(header: Sequence[str], aliases: tuple[str, ...]) -> str | None:
    lowered = {name.lower(): name for name in header}
    return next((lowered[alias] for alias in aliases if alias in lowered), None)


def _read(path: Path) -> list[_Row]:
    if not path.is_file():
        raise GaxisError("data_not_found", f"input table not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=_delimiter(path))
        header = reader.fieldnames or []
        sample = _pick(header, SAMPLE_ALIASES)
        gene = _pick(header, GENE_ALIASES)
        if not sample or not gene:
            raise GaxisError(
                "data_contract_violation",
                f"input needs a sample and a gene column; got {header}",
                hint="expected sample,gene[,gene_class] (one observed gene per sample)",
            )
        class_column = _pick(header, CLASS_ALIASES)
        rows: list[_Row] = []
        for record in reader:
            sample_value = (record.get(sample) or "").strip()
            gene_value = (record.get(gene) or "").strip()
            if not sample_value or not gene_value:
                continue
            class_value = (record.get(class_column) or "").strip() if class_column else ""
            rows.append(_Row(sample_value, gene_value, class_value))
    if not rows:
        raise GaxisError("empty_input", "the input table has no observed genes")
    return rows


def run_amr_cooccurrence(
    input_path: Path,
    *,
    out_dir: Path,
    params: AmrCooccurrenceParams | None = None,
    data_root: Path | None = None,
) -> AnalysisRun:
    params = params or AmrCooccurrenceParams()
    rows = _read(input_path)
    samples = sorted({row.sample for row in rows})
    gene_samples: dict[str, set[str]] = {}
    gene_class: dict[str, str] = {}
    for row in rows:
        gene_samples.setdefault(row.gene, set()).add(row.sample)
        if row.gene_class and row.gene not in gene_class:
            gene_class[row.gene] = row.gene_class

    genes = sorted(
        gene
        for gene, present in gene_samples.items()
        if len(present) / len(samples) >= params.min_prevalence
    )
    if not genes:
        raise GaxisError(
            "no_genes_pass_filter",
            "every gene is below min_prevalence",
            hint=f"try --min-prevalence {params.min_prevalence / 2:g}",
        )

    edges: list[dict[str, Any]] = []
    for left, right in itertools.combinations(genes, 2):
        both = len(gene_samples[left] & gene_samples[right])
        if both < params.min_support:
            continue
        union = len(gene_samples[left] | gene_samples[right])
        jaccard = both / union if union else 0.0
        weight = jaccard if params.weight == "jaccard" else float(both)
        edges.append(
            {
                "source": left,
                "target": right,
                "weight": round(weight, 6),
                "support": both,
                "jaccard": round(jaccard, 6),
            }
        )
    if not edges:
        raise GaxisError(
            "no_edges_pass_filter",
            "no gene pair co-occurs often enough",
            hint=f"try --min-support {max(1, params.min_support - 1)}",
        )

    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    run_id = hashlib.sha256(
        f"amr-cooccurrence-v1:{digest}:{params.model_dump_json()}".encode()
    ).hexdigest()[:10]
    target = out_dir / run_id
    target.mkdir(parents=True, exist_ok=True)

    nodes_path = target / "nodes.csv"
    with nodes_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["gene", "samples", "prevalence", "gene_class"])
        writer.writeheader()
        for gene in genes:
            writer.writerow(
                {
                    "gene": gene,
                    "samples": len(gene_samples[gene]),
                    "prevalence": round(len(gene_samples[gene]) / len(samples), 6),
                    "gene_class": gene_class.get(gene, ""),
                }
            )
    edges_path = target / "edges.csv"
    with edges_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["source", "target", "weight", "support", "jaccard"]
        )
        writer.writeheader()
        writer.writerows(edges)

    run = AnalysisRun(
        run_id=run_id,
        recipe="amr-cooccurrence",
        input_path=str(input_path),
        input_sha256=digest,
        params=params.model_dump(),
        samples=len(samples),
        genes=len(genes),
        edges=len(edges),
        outputs={"nodes": str(nodes_path), "edges": str(edges_path)},
        tool=f"gaxis {__version__}",
    )
    (target / "analysis.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return run
