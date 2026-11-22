# Quick Start

Goal: go from zero to a journal figure with script and manifest in 10 minutes, and know how to verify the result.

## 1. Prerequisites

| Dependency | Purpose | Required |
|---|---|---|
| [pixi](https://pixi.sh) | Provides Python 3.12, matplotlib, R + ggplot2 | Required |
| rootless podman | Sandbox for paper code (`gaxis reproduce`) | Needed for reproduction |
| gbrain + bun | Local knowledge base and retrieval | Needed for chart selection / reproduction / KB ingestion |
| Network | Paper downloads, repository cloning, per-paper mirror builds | Only needed for the paper workflow |

```bash
pixi install
pixi run gaxis health
```

`health` is a read-only probe that reports backend, preset, and per-stage readiness:

```json
{"ok": true, "version": "0.1.0", "python_backend": true, "r_backend": true,
 "presets": ["default", "nature", …], "stages": {"python": "ready", "r": "ready"}}
```

## 2. Configuration (Optional)

gaxis works out of the box with its default values. To change preset defaults, the data directory, or knowledge base toggles, copy `gaxis.example.toml` to `gaxis.toml`:

```bash
cp gaxis.example.toml gaxis.toml
pixi run gaxis config          # show the effective config (file + env overrides)
```

Configuration precedence: `--config` > `$GAXIS_CONFIG` > `./gaxis.toml` > `~/.config/gaxis/config.toml` > defaults.
See the [configuration reference](reference/configuration.md) for the full field list.

## 3. Your First Figure

```bash
pixi run gaxis describe --data examples/demo/expr.tsv
```

It outputs column types, cardinality, unit hints, and recommended encodings. Then:

```bash
pixi run gaxis render \
  --data examples/demo/expr.tsv \
  --preset nature_microbiology \
  --out data/demo
```

```
figure: bar-65ca394dac
dir:    /…/data/demo/bar-65ca394dac
figure.py   bar-65ca394dac.pdf   bar-65ca394dac.png   manifest.json
lint: clean
```

`figure.py` contains complete, directly runnable matplotlib code: change labels, change colors, change the statistical treatment — none of it requires gaxis.

## 4. Switching Backends and Chart Types

```bash
# ggplot2 backend
pixi run gaxis render --data examples/demo/expr.tsv --backend r --preset asm --out data/demo-r

# pick the chart type and encoding
pixi run gaxis render --data examples/demo/expr.tsv \
  --chart line --x time_h --y od600 --hue genotype --preset isme
```

8 chart types: `bar`, `stacked_bar`, `line`, `scatter`, `box`, `heatmap`, `network`, `tree`.
See [journal presets](presets.md) for the 7 presets.

## 5. Checking Deliverable Quality

```bash
pixi run gaxis lint data/demo/<figure-id>/<figure-id>.pdf --preset nature_microbiology
pixi run gaxis manifest data/demo/<figure-id>/manifest.json --json
```

The lint rules cover vector output, DPI, Type3 fonts, geometric dimensions, font fallback, colorblind-safe palettes, and missing labels (L001–L009).
The `data.sha256` and `code_sha256` in the manifest are evidence, not decoration.

## 6. Setting Up the Knowledge Base (Prerequisite for Chart Selection and Reproduction)

```bash
pixi run gbrain-install     # first run: vendor gbrain + pinned bun
pixi run gbrain-init        # create the brain under ${XDG_DATA_HOME:-~/.local/share}/gaxis/gbrain
pixi run gaxis kb status
pixi run gaxis kb seed      # 84 verified templates (offline, ~2-3 min)
```

After that:

```bash
pixi run gaxis kb search "rarefaction curve" --k 3
pixi run gaxis kb search --schema examples/demo/expr.tsv --sheet
```

## 7. Starting the MCP Server (Host Integration)

```bash
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
pixi run gaxis-mcp --transport http --port 8770
```

It refuses to start without a token; `stdio` is for local debugging only. See the [MCP tool contract](mcp-tools.md) for the tool list and per-tool contracts.

## Next Steps

- Follow the [tutorial](tutorial/index.md) to go through chart selection, adaptation, reproduction, panel assembly, and operations one by one;
- Or jump straight to the [command-line reference](reference/cli.md).
