# 09 SNP tree workflow (Snakemake)

## Goal

For analyses whose tools gaxis does not ship (IQ-TREE, alignment tools), gaxis **generates and
validates a Snakemake workflow**; bacmap (or you) runs it, and the tree is the input to a figure.
No phylogenetic algorithm is implemented in gaxis.

## Scaffold

```bash
pixi run gaxis analysis scaffold snp-tree \
  --out workflows/snp-tree \
  --alignment alignment.fasta \
  --container docker://<pinned-iqtree-image> \
  --threads 8 --check
```

Writes:

```
workflows/snp-tree/
  Snakefile
  config.yaml        alignment, model, bootstrap, threads, seed, container
  README.md
  workflow.json      recipe id, version, inputs/outputs, files sha256
```

`--check` runs `snakemake -n` (dry run) — config and DAG only, no tool execution.

## Run

```bash
cd workflows/snp-tree
snakemake --cores 8
```

Outputs:

```
results/tree.nwk
results/iqtree.log
```

- Set `container` to a **pinned** IQ-TREE image (digest preferred) before running on another machine.
- `metadata` is optional and reserved for tree annotation in the next step.
- bacmap can schedule the same Snakefile; gaxis is not in the execution path.

## Join tip metadata (optional)

```bash
pixi run gaxis analysis run newick-to-table \
  --input results/tree.nwk --metadata metadata.csv --out data/analysis
```

`metadata.csv` needs a key column (`tip`, `sample`, `id`, `name`, `genome`, `strain` or
`isolate`) plus any annotation columns; values are copied onto tip rows, so the tree table
gains `source`, `amr_class`, etc. Missing tips are listed in `metadata_missing.txt` inside the
run directory instead of being guessed.

## Render the tree

```bash
pixi run gaxis analysis run newick-to-table \
  --input results/tree.nwk --out data/analysis

pixi run gaxis render \
  --data data/analysis/<run_id>/tree_edges.csv \
  --chart tree --x parent --y child --weight branch_length \
  --hue source --annotation amr_class --preset asm --out data/figures
```

Rectangular cladogram, branch lengths from `branch_length`, tip labels, and one coloured strip
per annotation column (`--hue source` plus `--annotation amr_class`; repeat `--annotation` for
more) with a combined legend. matplotlib and ggplot2 both
render it. The tree itself still comes from IQ-TREE, not gaxis.

![Annotated tree example](/gaxis/assets/example-tree.png)

## Validate another checkout

```bash
pixi run gaxis analysis check workflows/snp-tree
```

## What gaxis does / does not do

| Does | Does not |
|---|---|
| generate the Snakefile + config + usage | run IQ-TREE or alignment tools |
| validate the DAG with `snakemake -n` | invent phylogenetic parameters |
| record inputs, outputs, file hashes | hide tool versions (container is explicit) |

## Checkpoints

- [ ] `workflow.json` has the inputs, outputs and `files_sha256`;
- [ ] `gaxis analysis check` returns `workflow OK`;
- [ ] `snakemake -n` reports the two expected outputs;
- [ ] after a real run, `results/tree.nwk` exists and the container is pinned.

## Next

Multi-column annotation strips (source + AMR class + type side by side) and shared legends with
the AMR network figure are the next step; the single-column annotation and workflow output are
stable contracts.
