# 02 Requirement or Data → Choose a Figure

## Goal

Before drawing anything, first pull **viewable candidate figures** from the knowledge base, pick one by hand, then decide whether to "render following its structure" or "adapt its code".
This section is fully offline (assuming the KB has been seeded).

## Approach A: Give a one-sentence requirement

```bash
pixi run gaxis plan "grouped bar with error bars, Nature Microbiology"
```

It outputs a data-independent plan: chart type, required column roles, style hints, questions to confirm, and matching cases from the knowledge base
(`matches[]`, including thumbnail paths and scores).

## Approach B: Data only

No need to write a query. gaxis first profiles the table, infers the chart type and encodings, then uses that to search:

```bash
pixi run gaxis kb search --schema examples/demo/expr.tsv --k 8 --sheet
```

```
8 hit(s)  degraded=False
sheet: /…/data/kb/sheets/search-3b5827d227/contact-sheet.png
  pdf-0883b2ad/fig-1   bar    L2   sim=- img=-
  ...
```

!!! tip "The candidate set should be viewable"
    `--sheet` generates a numbered contact sheet (`#1 … #N`), which is meant for **humans** to pick a figure; a plain JSON response is suited to host-side rendering.

![Candidate figure contact sheet](/gaxis/assets/example-candidates.png)

## Filtering: keep only what is worth picking

```bash
# only figures judged gold
pixi run gaxis kb search "bar chart" --tier gold

# only figures with recorded code (reproducible later)
pixi run gaxis kb search "bar chart" --has-code

# dedupe similar figures (on by default; --no-dedupe to inspect)
pixi run gaxis kb search "bar chart" --k 20
```

Composable: `--tier gold --has-code --chart bar`.

## Find a figure with an image

```bash
pixi run gaxis kb search "bar chart" \
  --image data/corpus/single-figures/review/cand-03.png --k 5
```

Perceptual hashing (dHash) ranks by shape and outputs a similarity such as `img=0.66`. It is a **shape signal**, not a semantic model:
it can find figures that "look alike", but not figures that "mean the same yet differ in structure".

## Pick one, then render

Suppose you pick `pdf-0883b2ad/fig-1` (or some template); record it when rendering:

```bash
pixi run gaxis render --data examples/demo/expr.tsv --preset asm \
  --source-asset template:asm-bar-python --out data/demo
```

Two effects:

1. `manifest.asset_ids` records the source asset — figures are no longer unattributed;
2. a selection record is appended to `data/kb/selections.jsonl`:

```json
{"recorded_at": "...", "asset_id": "template:asm-bar-python", "action": "render",
 "figure_id": "bar-43e3d19d74", "preset": "asm", "chart_type": "bar"}
```

The selection feedback is an **append-only** local log used to calibrate ranking; write failures are logged as warnings and do not block rendering.

## "Render" or "adapt"?

| Your situation | Choice |
|---|---|
| The KB holds a paper figure, but you don't have its data/code | Use its **structure** as a reference and `render` your own data (`--source-asset` records the source) |
| The KB holds a **validated template**, and the column names differ | `adapt` (next section): reuse the template code and change only the bindings |
| You have a paper's code and have already reproduced it | `kb adopt` → `adapt` (Section 04) |

## Checkpoints

- [ ] `contact-sheet.png` exists and its numbering matches the terminal order;
- [ ] the selected asset id appears in `manifest.asset_ids`;
- [ ] `data/kb/selections.jsonl` has a corresponding record;
- [ ] `--tier gold` really returns only gold (otherwise the page frontmatter lacks `design_tier`; run `quality backfill` first).

## Common issues

**`bad_parameter: give a query, a schema_path, or both`**: both were empty. Provide at least one.

**No candidates but the KB has pages**: first check whether `gaxis kb status` reports `available=False`; then check whether the query is too specific.
When a strict filter (e.g. `--chart heatmap`) returns no results, gaxis automatically falls back to plain-text matching and says so in the message.

**Missing thumbnails**: the file pointed to by the page's `image_path` does not exist (the data directory was cleared). Re-run `gaxis kb ingest`,
which rebuilds pages and paths from the manifest.
