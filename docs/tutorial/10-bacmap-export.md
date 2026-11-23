# 10 bacmap results → gaxis network

## Goal

Use AMR calls that already exist in a **bacmap results run**, not raw reads: export the tables,
compute co-occurrence, render a publication network. No AMR tool is re-run.

## Export the tables

```bash
python integrations/bacmap_export.py \
  --run-dir ~/.local/share/bacmap/results/runs/<run-id> \
  --out data/bacmap-export
```

Outputs:

```
data/bacmap-export/amr_long.csv   sample,gene,gene_class
data/bacmap-export/metadata.csv   sample,species,serotype
data/bacmap-export/export.json    samples, amr_rows, sources
```

The reference adapter is ~100 lines, stdlib only, and imports neither bacmap nor gaxis. In
bacmap, the same tables can be produced by its own result/query tools; the contract is the CSV.

## One call (optional)

If you have the long AMR table, `--run-analysis` runs the recipe's analysis first:

```bash
pixi run gaxis recipe render amr-network \
  --data data/bacmap-export/amr_long.csv --run-analysis \
  --analysis-param min_prevalence=0.3 --analysis-param min_support=2 \
  --out data/figures
```

The manifest records both `recipe_id` and `analysis_run_id`. A **composite** recipe goes further:

```bash
pixi run gaxis recipe render amr-summary \
  --data data/bacmap-export/amr_long.csv --run-analysis \
  --analysis-param min_prevalence=0.3 --color-map palette.json \
  --out data/figures
```

This runs the co-occurrence analysis once, renders the network and prevalence panels at the
composition preset, and returns a 1×2 `CompositionManifest` with A/B labels. To use already
computed tables, pass `--table edges=... --table nodes=...` instead of `--run-analysis`.

bacmap can still precompute the tables and call `recipe render` without `--run-analysis`.

## Analyse and render

```bash
pixi run gaxis analysis run amr-cooccurrence \
  --input data/bacmap-export/amr_long.csv --out data/analysis \
  --min-prevalence 0.3 --min-support 2

pixi run gaxis render \
  --data data/analysis/<run_id>/edges.csv \
  --chart network --x source --y target --weight weight \
  --color-map data/analysis/<run_id>/palette.json \
  --preset asm --out data/figures
```

Real example (20 Salmonellae, 121 AMR rows, 9 genes / 20 edges at `--min-prevalence 0.3`):

![bacmap network example](/gaxis/assets/example-bacmap-network.png)

`--min-prevalence` is both a scientific and a layout choice: lower values show more genes and a
denser network; raise it for a readable main figure, keep the dense version as a supplement.

## Multi-panel figure (network + prevalence)

```bash
pixi run gaxis recipe render amr-network   --data data/analysis/<amr>/edges.csv --color-map data/analysis/<amr>/palette.json   --out data/panels
pixi run gaxis recipe render amr-prevalence-bar   --data data/analysis/<amr>/nodes.csv --color-map data/analysis/<amr>/palette.json   --out data/panels

pixi run gaxis compose \
  --panels data/panels/<network-id>/manifest.json,data/panels/<bar-id>/manifest.json \
  --layout 1x2 --preset asm --uniform --out data/figures
```

`--uniform` re-renders both panels at the composition preset/cell size, and the bar recipe rotates
long gene labels by 90° so a 1×2 page stays readable.

![bacmap composite example](/gaxis/assets/example-bacmap-composite.png)

## What stays in bacmap

- assembly, typing, serotype, AMR calling, cgMLST;
- sample/run metadata and access control;
- the decision of which samples belong to a figure.

gaxis only sees the exported table, computes co-occurrence, and records the input hash in
`analysis.json`.

## Checkpoints

- [ ] `export.json` reports the run dir and row counts;
- [ ] `amr_long.csv` has one row per observed gene per sample;
- [ ] `analysis.json` has the input sha256 and parameters;
- [ ] the figure manifest has data/code hashes and lint is clean.
