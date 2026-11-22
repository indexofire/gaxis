# 08 AMR co-occurrence network (bacmap tables)

## Goal

Take AMR calls that already exist in bacmap (or any AMR screening table), compute gene
co-occurrence, and render a publication network — **without re-running ABRicate/AMRFinder**.
This is the first "analysis recipe": a table → table step, followed by gaxis rendering.

## Input contract

One row per observed gene per sample (long format):

```csv
sample,gene,gene_class
S1,blaCTX-M,beta-lactam
S1,blaTEM,beta-lactam
S1,sul1,sulfonamide
...
```

- `sample` aliases: `sample_id`, `genome`, `isolate`, `strain`;
- `gene` aliases: `amr_gene`, `feature`, `determinant`;
- optional class aliases: `gene_class`, `class`, `category`, `resistance_class`.

Absence is implied. The recipe does **not** call AMR tools; it consumes their output.

## Run the analysis

```bash
pixi run gaxis analysis run amr-cooccurrence \
  --input amr_long.csv --out data/analysis \
  --min-prevalence 0.05 --min-support 2 --weight jaccard
```

Output:

```
data/analysis/<run_id>/
  nodes.csv     gene,samples,prevalence,gene_class
  edges.csv     source,target,weight,support,jaccard
  analysis.json input sha256, params, counts, tool version
```

Edges are pairs whose shared-sample support is at least `--min-support` and whose Jaccard
(or shared count) is recorded as `weight`.

## Render the network

```bash
pixi run gaxis render \
  --data data/analysis/<run_id>/edges.csv \
  --chart network --x source --y target --weight weight \
  --preset asm --out data/figures
```

- circular layout, edge width/alpha from `weight`, node size from degree;
- both matplotlib and ggplot2 (same data contract);
- output is the usual deliverable: `figure.py` / `figure.R`, PDF/SVG/PNG/TIFF, lint, manifest.

![AMR network example](/gaxis/assets/example-amr-network.png)

## What it deliberately does not do

- No assembly, typing, AMR calling, or genome QC — bacmap/gmlst/gspec/gside already did that.
- No invented edges: the table is the evidence; `analysis.json` records the input hash.
- No hardcoded results: swap `edges.csv` and re-render; the figure changes.

## Checkpoints

- [ ] `nodes.csv`/`edges.csv` exist and `analysis.json` has the input sha256;
- [ ] `render` lint is clean on both backends;
- [ ] `manifest.json` has data/code hashes;
- [ ] changing `--min-support` changes the edge count (not just the drawing).

## Common issues

**`data_contract_violation`** — the input lacks a sample or gene column; check the header aliases.

**`no_edges_pass_filter`** — lower `--min-support`/`--min-prevalence`; a sparse matrix can
legitimately have no co-occurring pairs.

**Labels overlap** — circular layout keeps labels outside the ring; for many genes, filter to
the top classes or split by class into panels.
