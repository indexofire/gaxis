# 01 First figure: data to delivery

## Goal

Generate a journal-quality figure from a single CSV/TSV table and get three things: a figure, a standalone script, and a manifest. Then modify the script, re-run it, and confirm the results are still under control.

## Prepare the data

Any tidy table works. Example data:

```text
sample,genotype,condition,expr_fpkm,od600,time_h
WT_LB_0,WT,LB,114.93,0.372,0
WT_LB_1,WT,LB,124.35,0.366,6
...
```

Requirements: one observation per row, column names in the first row, comma- or tab-separated, UTF-8 encoding (with BOM is also fine).

## Step 1: Let gaxis read the table

```bash
pixi run gaxis describe --data examples/demo/expr.tsv
```

You will see each column's type (numeric/categorical), cardinality, unit hints, and the recommended chart types.

## Step 2: Render

```bash
pixi run gaxis render \
  --data examples/demo/expr.tsv \
  --preset nature_microbiology \
  --out data/demo
```

```
figure: bar-65ca394dac
dir:    /…/data/demo/bar-65ca394dac
wrote:  /…/data/demo/bar-65ca394dac/bar-65ca394dac.pdf  (89 x 60 mm @600 dpi)
wrote:  /…/data/demo/bar-65ca394dac/bar-65ca394dac.png
lint:   clean
```

If lint has issues, the command still writes files, but the exit code is 3 (unless you pass `--allow-lint-errors`).
This is deliberate: you get the figure, but problems are not allowed to hide.

## Step 3: Read the manifest

```bash
pixi run gaxis manifest data/demo/bar-65ca394dac/manifest.json --json
```

Key fields:

| Field | Meaning |
|---|---|
| `figure_id` | hash prefix of `PIPELINE_VERSION + data.sha256 + spec` |
| `data.sha256` | content hash of the input table |
| `code_sha256` | content hash of the generated script |
| `spec` | encoded intent (chart type, x/y/hue, preset, backend, geometry) |
| `lint.issues[]` | itemized checks and their locations |
| `outputs[]` | measured geometry and DPI of each output artifact |

## Step 4: Modify the script

Open `figure.py` — it is just an ordinary matplotlib script. For example, change the y-axis label to include the unit:

```python
ax.set_ylabel("expression (FPKM)")
```

Then run it directly:

```bash
cd data/demo/bar-65ca394dac
python figure.py
```

!!! note "The deliverables do not depend on gaxis"
    There is no `import gaxis` in the script. This is a product requirement, not a coincidence: it must run on the machines of reviewers, collaborators, and you three years from now.

## Step 5: Switch backend and preset

```bash
# R / ggplot2
pixi run gaxis render --data examples/demo/expr.tsv --backend r --preset asm --out data/demo-r

# Change chart type and encodings
pixi run gaxis render --data examples/demo/expr.tsv \
  --chart line --x time_h --y od600 --hue genotype --preset isme
```

Both backends share the same data grouping and statistical conventions (`summarise()`), so for the same spec the matplotlib and ggplot2
outputs should be structurally identical.

## Do the same thing via MCP

The equivalent call from the host:

```json
{"data_path": "/abs/expr.tsv", "preset": "nature_microbiology",
 "chart_type": "bar", "x": "genotype", "y": "expr_fpkm", "hue": "condition"}
```

It returns `figure_id`, `code_path`, `outputs[]`, `lint`, `manifest`. The host should also show `code_path` to the user,
otherwise the "figure" becomes a black-box artifact.

## Checkpoints

- [ ] `data/demo/<id>/figure.py` does not import gaxis and runs successfully on its own;
- [ ] both `data.sha256` and `code_sha256` in `manifest.json` are non-empty;
- [ ] `lint: clean` (or you explicitly accept a given issue);
- [ ] the same spec with `--backend r` also produces a lint-clean figure.

## Common issues

**`unknown_column`**: the `--x/--y/--hue` names do not match the table headers. Run `gaxis describe` first to see the available column names.

**`not_numeric`**: the y for heatmap/scatter/box must be a numeric column; check for non-numeric strings other than `"NA"`.

**Size does not match the preset**: `--width/--height` overrides the preset geometry; re-check with `gaxis lint` before submission.
