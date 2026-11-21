# 05 Multi-Panel Composition

## Goal

Assemble several already-rendered panels into a single submission figure: vectors preserved, panels labeled A/B/C, controllable page size, and a manifest for the composition process.
The optional `--uniform` flag **re-renders** all panels with the same preset and the same cell size, so font sizes and line widths are consistent.

## Prerequisites

Every panel must already be rendered (with its own `figure.py` and manifest). Composition does **not redraw**; it only arranges PDF pages.

```bash
pixi run gaxis render --data examples/demo/expr.tsv --chart bar --preset nature_microbiology --out data/demo
pixi run gaxis render --data examples/demo/expr.tsv --chart line --x time_h --y od600 --out data/demo
```

This yields two figure ids, e.g. `bar-b7d31efe17` and `line-3b81d186c6`.

## Basic Composition

```bash
pixi run gaxis compose \
  --panels bar-b7d31efe17,line-3b81d186c6 \
  --layout 1x2 --preset nature_microbiology \
  --out data/demo/composition
```

```
composition: composition-8cbe3c3a38
layout:      1x2  183.0x71.4 mm
pdf:         …/composition-8cbe3c3a38.pdf
png:         …/composition-8cbe3c3a38.png
  A  bar-b7d31efe17
  B  line-3b81d186c6
lint: clean
```

![Composition example](/gaxis/assets/example-composition.png)

## Layout and Labels

- `--layout ROWSxCOLS`; if omitted, automatic: ≤3 panels use 1×n, 4 use 2×2, more use a near-square grid.
- `--no-labels` removes the A/B/C labels; they are added by default.
- `--width/--height` (mm) override the default page size; by default the preset's double-column width is used.
- Panels can be given as figure ids, or directly as `manifest.json` paths (handy when using a custom `--out`).

## Uniform Typography: `--uniform`

The default is "place as-is": each panel keeps the font size and geometry from its own rendering. To unify them:

```bash
pixi run gaxis compose \
  --panels bar-b7d31efe17,line-3b81d186c6 \
  --layout 1x2 --preset asm --uniform \
  --out data/demo/composition
```

`--uniform` **re-renders each panel** with the composition preset and cell size (using the spec and data from each panel's own manifest), then places them. As a result:

- Font sizes, line widths, and fonts are consistent;
- Each panel's data file must still be readable, otherwise an explicit `data_not_found` is reported;
- The composition manifest's `panels[].manifest_id` points to the **re-rendered** panels, and `code_sha256` is new as well.

![Uniform typography example](/gaxis/assets/example-composition.png)

## Composition manifest

```bash
pixi run gaxis manifest data/demo/composition/composition-8cbe3c3a38.json --json
```

```json
{"composition_id": "composition-8cbe3c3a38",
 "panels": [{"manifest_id": "bar-b7d31efe17", "label": "A", "code_sha256": "…"}],
 "layout": [1, 2], "width_mm": 183.0, "height_mm": 71.4,
 "uniform": false, "lint": {"ok": true}}
```

It is the evidence of the composition: every panel's code hash is included, so any panel that gets swapped can be traced.

## Limitations (explicit design boundaries)

- Only vector panels are accepted: PNG-only panels report `panel_not_vector` and are not silently rasterized.
- The layout only supports rectangular grids: no nesting (1×3+2), no shared axes across panels, no legend merging.
- `--uniform` means "re-render, then place", not "change each panel's internal layout at composition time".

## Checklist

- [ ] Each panel in the output PDF is still vector after opening (text selectable / no blur when zoomed);
- [ ] Labels match `panels[].label`;
- [ ] Page size matches `width_mm/height_mm` (within ±2%);
- [ ] The composition lint is clean.

## Common Issues

**`figure_not_found`**: the id is neither in `data/renders` nor in the data directory. Using a `manifest.json` path is more reliable.

**`bad_layout`**: the grid cannot fit that many panels. Use a larger grid (e.g. `2x2`) or fewer panels.

**`panel_not_vector`**: a panel was rendered as PNG only. Re-run `render --formats pdf`.
