# gaxis

**Turn a tidy data table into a publication-grade figure and hand you back the script that produced it; turn the figures in a paper into reproducible, searchable, reusable code.**

gaxis has two usage surfaces that share the same core:

| Interface | Who it's for | Entry point |
|---|---|---|
| **CLI** | Researchers at the terminal, offline, no knowledge base needed | `pixi run gaxis …` |
| **MCP server** | Hosts such as bacmap, Pi, DSH, Hermes; Streamable HTTP + Bearer | `pixi run gaxis-mcp` |

The core principle is a single sentence:

> The figure, the script, and the manifest are one and the same artifact. Any design in which two of them can drift apart is wrong.

![Example figure](/gaxis/assets/example-figure.png)

## What it can do

- **Figures**: 6 figure types × matplotlib / ggplot2 dual backends × 7 microbiology journal presets, PDF/SVG/PNG/TIFF, item-by-item publication-grade lint (L001–L009).
- **Deliverable code**: every figure ships with a standalone `figure.py` / `figure.R` that does not import gaxis and runs in any Python/R environment.
- **Evidence binding**: every render writes a `manifest.json` containing the data hash, code hash, output geometry, and lint report.
- **Figure selection**: give a one-sentence requirement, or just a data table, and it retrieves candidate figures from the knowledge base, generates a numbered contact sheet, then renders the one you pick.
- **Paper figure reproduction**: parse the PDF → locate figures, captions, cited sections, and code repositories → run in a podman sandbox → visual comparison → L1/L2/L3 grading.
- **LLM reconstruction fallback**: when author code is missing or broken, a vision model writes a new script and the sandbox grades it; the manifest records `method = llm_reconstruction`/`llm_repair`, never `author_code`.
- **Code ingestion**: successfully reproduced scripts are automatically copied into the asset library and KB pages refreshed; verified templates can be re-bound to new data (`adapt`).
- **Panel layout**: arrange rendered panels on a single page (vectors preserved), with optional `--uniform` to unify font sizes and geometry.
- **Queues and self-healing**: checkpointed ingestion/reproduction queues, retries, stall reclamation, heartbeats, evidence verification.

## Up and running in 60 seconds

```bash
# 1. environment (pixi installs python 3.12, matplotlib, R + ggplot2)
pixi install
pixi run check                      # ruff + mypy + the full test suite

# 2. render a Nature Microbiology style bar chart from the demo data
pixi run gaxis render --data examples/demo/expr.tsv --preset nature_microbiology --out data/demo

# 3. see what it hands back
ls data/demo/<figure-id>/            # figure.py  <figure-id>.pdf  manifest.json
```

When `examples/demo` is not available, any CSV/TSV will do:

```bash
pixi run gaxis describe --data my_table.csv
pixi run gaxis render --data my_table.csv --preset asm --out out/
```

## Knowledge base (optional, but recommended)

```bash
pixi run gbrain-install      # first run: vendored gbrain + pinned bun
pixi run gbrain-init         # create the brain under ~/.local/share/gaxis/gbrain
pixi run gaxis kb seed       # 84 verified templates (~2-3 min, offline)
pixi run gaxis kb status     # 96 pages, missing_embeddings=0
```

The knowledge base is a **rebuildable artifact** and is not distributed with the repository; pages are generated from manifests, so if you wipe it, just rerun the three steps above.

## Where to start

- First time here → [Quick start](quickstart.md)
- Want to know "why are figure/script/manifest bound together" → [Core concepts](concepts.md)
- Want to follow along → [Tutorial](tutorial/index.md)
- Look up commands and configuration → [CLI](reference/cli.md) · [Configuration](reference/configuration.md)
- Wire up MCP for a host → [MCP tool contract](mcp-tools.md)

## Explicit non-goals

gaxis does not do species/genome data retrieval, does not do analysis pipelines, does not do meta-databases, and does not call LLMs in the render path. Figures are deterministic: given a manifest, the same version should reproduce byte-for-byte.
