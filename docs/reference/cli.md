# Command-Line Reference

All commands are run via `pixi run gaxis …` (the installed `gaxis` may also be called directly).
On failure the exit code is non-zero, the error is printed as `{"code", "message", "hint?"}`, and `--json` provides machine-readable output.

## Global

| Command | Purpose |
|---|---|
| `gaxis version` | Version |
| `gaxis config` | Effective configuration (file + environment variables) |
| `gaxis health` | Read-only health check |
| `gaxis tools` | Frozen MCP tool contract (v2.1) |
| `gaxis presets` | Journal preset geometry and font sizes |
| `gaxis palettes` | Palettes and colorblind-safe markers |

## Rendering

### `gaxis describe --data TABLE`

Profile a table: column types, cardinality, unit hints, recommended chart types.

### `gaxis render --data TABLE [options]`

| Option | Description |
|---|---|
| `--chart {bar,stacked_bar,line,scatter,box,heatmap,network,tree}` | Chart type (inferred; network/tree must be explicit) |
| `--x/--y/--hue/--yerr/--weight/--annotation/--color-map/--rotate-labels` | Encoded columns; `--color-map` is category→hex JSON; `--rotate-labels` is an x tick angle |
| `--backend python\|r` | matplotlib or ggplot2 |
| `--preset NAME` | Journal preset (default `default`) |
| `--palette NAME` | Override the preset palette |
| `--width/--height` | Override preset geometry (mm) |
| `--dpi` | Default 600 |
| `--formats pdf,png` | Combinable from `pdf,svg,png,tiff` |
| `--annotate` | Print values on the markers |
| `--out DIR` | Output root directory (default `data/renders`) |
| `--source-asset ID` | Record the source asset (selection feedback) |
| `--allow-lint-errors` | Still return 0 despite lint issues |

### `gaxis lint PATHS… [--preset NAME] [--width MM --height MM]`

Language-agnostic publication-grade checks on existing artifacts (L001–L009); multiple files may be passed at once.

## Planning & Selection

### `gaxis plan "BRIEF" [--preset NAME] [--k N]`

A data-independent chart plan + knowledge-base matched cases. Useful for aligning with the user/host before the data is ready.

### `gaxis kb search [QUERY] [options]`

| Option | Description |
|---|---|
| `--schema TABLE` | Search using the table schema (`QUERY` may be omitted) |
| `--image PATH` | Search using an image (dHash similarity) |
| `--chart TYPE` / `--min-level L1\|L2\|L3` | Filters |
| `--tier gold\|dense\|reject` | Filter by design tier |
| `--has-code/--no-code` | Whether a code record exists |
| `--k N` | Number of results (≤50) |
| `--sheet` | Generate a numbered contact sheet and print its path |
| `--json` | Machine-readable output |

## Templates & Adaptation

### `gaxis kb seed [--preset NAME]… [--backend python\|r]… [--force]`

Actually renders and validates a template for each (preset × chart type × backend) combination and writes `type: template` pages. Idempotent.

### `gaxis kb adopt MANIFEST_ID [--code PATH] [--preset NAME]`

Register an already-reproduced paper script as a template. The script must bind its inputs via `DATA_PATH`, otherwise `adoption_refused`.

### `gaxis adapt --data TABLE [options]`

| Option | Description |
|---|---|
| `--query TEXT` | Intent (e.g. `"grouped bar"`) |
| `--asset ID` | Specify the template page |
| `--preset NAME` / `--backend python\|r` | Select the template family |
| `--dry-run` | Write only the script and manifest without executing |
| `--json` | Machine-readable output |

## Papers

### `gaxis ingest SOURCE [--mode kb_first\|full] [--with-code/--no-code]`

`SOURCE` can be a PDF path, DOI, arXiv id, PubMed id, PMC id, or a PDF URL.
`kb_first` parses only figures and captions; `full` also downloads the PDF, finds repositories, and picks scripts.

### `gaxis manifest MANIFEST_ID|PATH [--json]`

View the full manifest of a paper figure by id (code candidates, reproduction level, scores); you can also pass the path to
`manifest.json` inside a render output directory to view the figure/code/data hashes and lint results.

### `gaxis reproduce MANIFEST_ID --code SCRIPT [--data FILE] [--engine podman\|local] [--allow-network]`

Single-figure reproduction → grading → automatic assetization + KB refresh.

### `gaxis recipe list` / `gaxis recipe render`

| Command | Meaning |
|---|---|
| `gaxis recipe list [--chart TYPE] [--json]` | curated table→figure contracts |
| `gaxis recipe render amr-network --data edges.csv [--color-map palette.json] [--out DIR] [--dry-run]` | check required columns, then render |
| `gaxis recipe render amr-network --data amr_long.csv --run-analysis [--analysis-param k=v]` | run the recipe's analysis first, then render |

`recipe render` uses the same contracts as `list_figure_recipes` / `render_figure_recipe` over MCP.

### `gaxis analysis list` / `gaxis analysis run`

| Command | Meaning |
|---|---|
| `gaxis analysis list [--json]` | available analysis recipes, input contract, outputs |
| `gaxis analysis run amr-cooccurrence --input TABLE [--out DIR] [--min-prevalence F] [--min-support N] [--weight jaccard\|count]` | table → `nodes.csv` + `edges.csv` + `analysis.json` |
| `gaxis analysis run newick-to-table --input tree.nwk [--metadata META] [--out DIR]` | Newick → `tree_edges.csv` (parent, child, branch_length) |
| `gaxis analysis workflows` | list Snakemake workflow recipes |
| `gaxis analysis scaffold snp-tree --out DIR --alignment FASTA [--container IMAGE] [--check]` | generate a validated IQ-TREE workflow project |
| `gaxis analysis check DIR` | validate an existing workflow with `snakemake -n` |

The AMR recipe consumes gene calls that already exist (bacmap/ABRicate). It does not run
AMR calling. Render the result with `--chart network --x source --y target --weight weight`.

### `gaxis reconstruct MANIFEST_ID [options]`

| Option | Meaning |
|---|---|
| `--data FILE` | input table mounted into the sandbox (`GAXIS_DATA`) |
| `--engine podman\|local` | sandbox engine |
| `--rounds N` | generate/revise rounds |
| `--target F` | stop at this similarity |
| `--repair` | start from the author script |
| `--model NAME` | override the configured vision/code model |
| `--timeout S` / `--max-side PX` | per-request timeout and image size |

### `gaxis reproduce-paper PAPER_ID [options]`

| Option | Description |
|---|---|
| `--data FILE` | Input table shared by all figures |
| `--synthetic` | Generate a flagged synthetic table when no data is available |
| `--min-confidence F` | Code-pairing confidence threshold (default 0.5) |
| `--limit N` | Maximum number of figures to process (default 8) |
| `--engine podman\|local` | Override configuration |
| `--force` | Re-run figures already graded L1/L2 |

## Composition

### `gaxis compose --panels ID[,ID…] [options]`

| Option | Description |
|---|---|
| `--layout ROWSxCOLS` | Automatic if omitted |
| `--preset NAME` | Preset for the composed page |
| `--width/--height` | Page size (mm) |
| `--uniform` | Re-render every panel according to the composition preset and cell size |
| `--no-labels` | Do not add A/B/C labels |
| `--out DIR` | Output directory |

## Knowledge Base

| Command | Purpose |
|---|---|
| `gaxis kb status` | Reachability, page count, missing vector count |
| `gaxis kb ingest [--force]` | Project all manifests into the KB (idempotent) |
| `gaxis kb seed` | Validate templates into the KB |
| `gaxis kb adopt` | Store paper scripts as templates |
| `gaxis kb search` | Search (see above) |

## Queue

| Command | Purpose |
|---|---|
| `gaxis ops enqueue SOURCE… [--kind ingest\|reproduce] [--mode …]` | Enqueue (deduplicated) |
| `gaxis ops run [--limit N] [--retries N] [--stall-minutes N]` | Process pending jobs |
| `gaxis ops verify` | Verify that evidence for `done` jobs still exists |
| `gaxis ops status [--reset all\|SOURCE] [--json]` | View/reset |

## Quality & Design (Maintainer Tools)

| Command | Purpose |
|---|---|
| `gaxis quality sheet` | Generate a manual ranking sheet (Markdown + contact sheet) |
| `gaxis quality backfill [--workers N] [--force]` | Recompute crop quality / design / usefulness and re-ingest |
| `gaxis quality calibrate CSV` | Fit weights from manual rankings |
| `gaxis design judge IMAGE` | Design review of a single image |
| `gaxis design judge-dir DIR` | Batch review and output a ranking CSV |
| `gaxis design candidates DIR` | Generate numbered sheets for an external figure set |

## MCP server

```bash
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
gaxis-mcp --transport http --host 127.0.0.1 --port 8770
gaxis-mcp --transport http --uds /tmp/gaxis.sock
gaxis-mcp --transport stdio          # local debugging only
```

It refuses to start without a token; HTTP is the production path.
