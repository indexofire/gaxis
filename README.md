# gaxis

English | [简体中文](README.zh.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Docs](https://img.shields.io/badge/docs-indexofire.github.io%2Fgaxis-4f46e5.svg)](https://indexofire.github.io/gaxis/)

Turning paper figures into **verified, reusable, publication-grade figure code** — and rendering
your own data in the same visual grammar.

Two surfaces over one core:

| Surface | Who | In | Out |
|---|---|---|---|
| MCP server (Streamable HTTP) | bacmap, DSH, Pi, Hermes, any MCP client | data path / paper query | figure + code + manifest |
| CLI | researchers at a terminal | `results.csv` | publication-grade figure + editable script |

## Status

**0.1.0** — the core loop works end to end:

- deterministic pipeline: data → spec → standalone script → figure → publication lint (L001–L009)
  → `manifest.json` with data/code hashes; eight chart types × matplotlib/ggplot2 × seven presets;
- paper side: identifier resolution, bounded PDF download, figure/caption/citing-paragraph
  extraction, repository link + plotting-script discovery;
- reproduction: rootless podman sandbox, similarity decomposition, L1/L2/L3, code assetisation;
- knowledge base: gbrain `paper-kb` pages, embeddings, text/schema/image retrieval, 84 verified
  templates (`kb seed`), paper-script adoption (`kb adopt`);
- selection & adaptation: `plan_chart_from_brief`, candidate contact sheets, `adapt_chart_code`,
  multi-panel `compose` (with `--uniform`);
- analysis recipes on bacmap tables: `gaxis analysis run amr-cooccurrence` computes gene
  co-occurrence (no AMR re-calling) and `--chart network` renders it in both backends;
  `integrations/bacmap_export.py` turns a bacmap results run into the required tables;
- curated recipes via `gaxis recipe list/render` (same contracts as the MCP tools);
- operations: checkpointed ingest/reproduce queue, retries, stall reclaim, heartbeat, `ops verify`;
- surfaces: CLI and MCP server (twelve tools, contract v2.9) + typed client + bacmap adapter.

M5 host adapters beyond CLI/bacmap and the deeper M6 self-healing layers are still in progress;
known limits are listed in [CHANGELOG.md](CHANGELOG.md#known-limits-in-010).

Docs: the user guide and tutorials are in [`docs/`](docs/index.md) (MkDocs Material:
`pixi run docs-serve` / `pixi run docs-build`). Architecture and ADRs: [DESIGN.md](DESIGN.md);
contributor rules: [AGENTS.md](AGENTS.md).

## Quick start

```bash
pixi install                          # python 3.12 + matplotlib + R/ggplot2
pixi run gaxis presets                # available journal presets
pixi run gaxis describe --data examples/demo/expr.tsv
pixi run gaxis render --data examples/demo/expr.tsv --chart bar \
  --x genotype --y expr_fpkm --hue condition --preset nature_microbiology \
  --out data/demo
pixi run gaxis render --data examples/demo/expr.tsv --preset asm \
  --backend r --out data/demo-r            # same figure via ggplot2
pixi run gaxis tools                   # frozen MCP contract + data classes
cp gaxis.example.toml gaxis.toml     # confirmation threshold, ingest mode, gbrain wiring
pixi run gaxis config                # effective configuration
pixi run gaxis plan "grouped bar chart with error bars, Nature Microbiology"
pixi run gaxis ingest examples/demo/paper.pdf --mode full   # paper -> figures + manifests
pixi run gaxis ingest 10.1099/mgen.0.000001      # DOI -> open-access PDF -> figures -> repo code
pixi run gaxis manifest pdf-<sha8>/fig-1
pixi run gaxis reproduce pdf-<sha8>/fig-1 --code examples/demo/figure.py --engine podman
pixi run gaxis reproduce pdf-<sha8>/fig-1 --code examples/demo/figure.R --engine podman
pixi run gaxis quality sheet            # ranking sheet (design columns; extraction is the gate)
pixi run gaxis design candidates <dir>  # numbered sheet for a curated golden set
pixi run gaxis design judge <image>     # score one figure with the configured vision judge
pixi run gaxis kb seed                     # verified templates for adapt_chart_code
pixi run gaxis adapt --data examples/demo/expr.tsv --preset asm --query "bar chart"
pixi run gaxis kb adopt pdf-<sha8>/fig-1 --code examples/demo/figure.py  # paper script -> template
pixi run gaxis kb search --schema examples/demo/expr.tsv --sheet  # choose from the KB by table shape
pixi run gaxis reproduce-paper pdf-<sha8> [--synthetic]       # reproduce a paper's figures
pixi run gaxis compose --panels a,b --layout 1x2 --preset nature_microbiology
pixi run gaxis ops enqueue <doi> examples/demo/paper.pdf && pixi run gaxis ops run
pixi run gaxis health                  # read-only probe

# knowledge base (gbrain), installed into the pixi env
pixi run gbrain-install && pixi run gbrain-init
pixi run gbrain search "rarefaction curve" --source-id paper-kb --json

# as a tool for bacmap / any MCP host
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
pixi run gaxis-mcp --transport http --port 8770
pixi run gaxis lint data/demo/<figure-id>/figure.pdf
pixi run check                        # ruff + mypy + pytest
pixi run review                       # 36-figure matrix + contact sheet for human review
```

Every render writes a self-contained directory:

```
data/demo/<figure-id>/
  figure.py | figure.R   # the deliverable: readable, runnable, no gaxis import
  figure.pdf figure.svg figure.png
  manifest.json          # spec + data sha256 + code sha256 + outputs + lint report
```

The script that produced the image is the script you get. There is no second
generation step that can drift from the artifact.

## Documentation

User guide and tutorials are built with MkDocs Material:

```bash
pixi run docs-serve   # preview at http://127.0.0.1:8000/gaxis/
pixi run docs-build   # strict build into site/
```

Start at `docs/index.md`; the tutorials cover first figure, selection, template adaptation,
paper reproduction, composition, and operations. Internal contracts stay under `docs/*.md`.

## Design notes

- `ChartSpec` is the only intermediate representation; producers (builtin templates, KB assets,
  paper reproduction) never talk to a renderer directly.
- `style/presets/*.toml` encodes journal geometry (widths in mm, font sizes in pt, palette,
  spines, vector font embedding) — microbiology first: Nature Microbiology, ASM (mBio/AEM),
  ISME J, Cell Host & Microbe, Microbial Genomics.
- `style/lint.py` is the measurable form of "publication grade": vector output, DPI, embedded
  fonts (no Type 3), figure geometry, colour-blind safety, required text labels.
- `manifest.json` carries `data.sha256` + `code.sha256` + lint report, so any delivered figure is
  auditable back to its input (ADR-08).
- Both backends aggregate identically (mean + SD, or a supplied `yerr` column) and fall back to
  count mode when no numeric measure is given, so a matplotlib figure and its ggplot2 twin are
  comparable, not merely similar.
- MCP tools declare `data_class` (`D1`–`D4`) and side effects, so a host such as bacmap can enforce
  its profile ceiling **before** a call touches local data.
