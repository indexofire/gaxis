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

Tree rendering (`tree.nwk` → publication tree with tip metadata) is the next step; the workflow
output is already the stable contract.
