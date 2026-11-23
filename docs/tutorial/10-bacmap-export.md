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
