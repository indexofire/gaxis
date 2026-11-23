# MCP tool reference — contract v2.8

Frozen surface between the gaxis kernel and every host. Source of truth:
`src/gaxis/models/tools.py`; snapshot: `tests/contract_snapshot.json`; refresh with
`pixi run python scripts/freeze_contract.py` (only after an intentional version bump).

## 0. Transport, auth, lifecycle

| Item | Value |
|---|---|
| Transport (production) | Streamable HTTP, `http://127.0.0.1:8770/mcp` |
| Transport (debug only) | stdio (`gaxis-mcp --transport stdio`) |
| Auth | `Authorization: Bearer $GAXIS_MCP_TOKEN`; the server refuses to start on HTTP without it |
| Bind | loopback by default; DNS-rebinding protection on configured hosts |
| Health | `health` is read-only; safe for timers and supervised restarts |
| Lifetime | the server is an independent process; hosts connect and disconnect freely (ADR-02) |

Start the server:

```bash
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
gaxis-mcp --transport http --host 127.0.0.1 --port 8770     # endpoint: /mcp
```

Clients (hosts, notebooks) should use the typed client rather than raw JSON-RPC:

```python
from gaxis.client import GaxisClient
from gaxis.models.tools import RenderRequest

async with GaxisClient("http://127.0.0.1:8770/mcp", token=token) as gaxis:
    schema = await gaxis.describe_data_schema("/abs/results.tsv")
    figure = await gaxis.render_chart_from_data(
        RenderRequest(data_path=schema.data_schema.path, preset="nature_microbiology")
    )
```

Kernel errors come back as `{"status": "error", "code", "message", "hint"?}`; `GaxisClient` raises
`GaxisError` so callers branch on codes, not prose.

Tool naming: gaxis exposes bare names (`render_chart_from_data`). Hosts that namespace their tools
(bacmap) rename them on their side (`bacmap_chart_render`) — renaming is an adapter concern, never a
kernel one.

## 1. Gating metadata (why every tool has one)

Each tool declares, in its machine-readable spec:

| Field | Meaning |
|---|---|
| `data_class` | `D1` public … `D4` local-only. Use `D3` when the call reads a local user file |
| `side_effects` | human-readable list; empty means the call cannot mutate |
| `needs_network` | true only for paper acquisition tools |
| `cost` | `ms`, `s`, `min`, `10min+` — for host-side scheduling and UI |
| `implemented` + `milestone` | lets a host hide stubs instead of surfacing failures |

Hosts that enforce data policy (bacmap `cloud` profile = D1 ceiling) filter on this **before** the
call. `pixi run gaxis tools` prints the whole catalog.

## 2. Tools

### 2.1 `health` — D1, no side effects

```json
// request
{}
// response
{
  "ok": true,
  "version": "0.1.0",
  "data_root": "/…/data",
  "python_backend": true,
  "r_backend": true,
  "presets": ["asm", "cell_host_microbe", "default", "isme", "microbial_genomics", "nature", "nature_microbiology"],
  "stages": {"render_chart_from_data": "ready", "search_chart_assets": "ready"},
  "message": "5 palettes, 7 journal presets"
}
```

Never triggers a render, a download or a write. Use it for liveness, and for verifying that the R
backend is actually installed before requesting a ggplot2 figure.

### 2.2 `describe_data_schema` — D3 (follows the input file), read-only

```json
// request
{"data_path": "/abs/path/results.tsv"}
// response (abridged)
{
  "data_schema": {
    "path": "/abs/path/results.tsv",
    "format": "tsv",
    "delimiter": "\t",
    "n_rows": 48,
    "sha256": "…",
    "columns": [
      {"name": "genotype", "kind": "categorical", "n_unique": 4, "missing_ratio": 0.0,
       "sample_values": ["WT", "dpsA", "rpoS"], "unit_hint": null},
      {"name": "expr_fpkm", "kind": "numeric", "n_unique": 47, "missing_ratio": 0.0,
       "sample_values": ["114.93", "124.35", "110.87"], "unit_hint": "FPKM"}
    ]
  },
  "suggested_spec": {"chart_type": "bar", "x": "genotype", "y": "expr_fpkm", "hue": "condition", "preset": "default"},
  "summary": "48 rows x 6 columns (results.tsv)\n- `genotype`: categorical, 4 unique, 0% missing, …"
}
```

Agent contract: call this first, then either accept `suggested_spec` or override specific fields.
Errors: `data_not_found`, `data_unreadable`.

### 2.3 `render_chart_from_data` — D3, executes a sandboxed script

```json
// request
{
  "data_path": "/abs/path/results.tsv",
  "chart_type": "bar",
  "x": "genotype", "y": "expr_fpkm", "hue": "condition",
  "preset": "nature_microbiology",
  "backend": "r",
  "formats": ["pdf", "png"],
  "dpi": 600,
  "out_dir": "/abs/path/project/figures"
}
// response (abridged)
{
  "figure_id": "bar-f485e439e0",
  "manifest_path": "…/bar-f485e439e0/manifest.json",
  "code_path": "…/bar-f485e439e0/figure.R",
  "outputs": [{"format": "pdf", "width_mm": 89.0, "height_mm": 60.0, "bytes": 8421, "dpi": null}],
  "lint": {"issues": []},
  "duration_s": 1.9
}
```

Guarantees: the returned script is self-contained (no gaxis import), the manifest carries
`data.sha256` + `code_sha256`, and lint errors are reported rather than hidden. A non-clean lint
result is still a successful render — decide policy at the host.

Errors: `unknown_column`, `not_numeric`, `missing_x`, `missing_y`, `render_failed`,
`bad_parameter`.

### 2.3b `plan_chart_from_brief` — D1, ready (heuristics)

Entry point of service flow 1: **no data required**. Turns a sentence into a plan the host LLM
converges on with the user.

```json
// request
{"brief": "grouped bar chart with error bars, Nature Microbiology, ggplot2, colour-blind palette"}
// response (abridged)
{
  "plan": {
    "brief": "…",
    "spec": {"chart_type": "bar", "preset": "nature_microbiology", "palette": "okabe_ito",
             "backend": "r", "x": null, "y": null, "hue": null},
    "required_columns": [
      {"role": "x", "kind": "categorical", "hint": "2-12 groups"},
      {"role": "y", "kind": "numeric", "hint": "measurement per observation (omit to count rows)"},
      {"role": "hue", "kind": "categorical", "hint": "grouping factor, 2-8 levels (colour/fill)"}
    ],
    "style_notes": ["error bars: mean ± SD across replicates by default; pass a `yerr` column …"],
    "open_questions": ["Error bars: SD, SEM, or 95% CI? (and how many replicates per group)",
                       "Attach the table (CSV/TSV, one observation per row) or describe its columns"],
    "confidence": 0.85
  },
  "matches": [], "degraded": true, "message": "knowledge base disabled ([knowledge] enabled = false) …",
  "requires_confirmation": false, "confirmation_threshold": 0.6, "confirmation_mode": "auto"
}
```

`requires_confirmation` is computed from `[confirmation]` in `gaxis.toml` (`mode` +
`min_confidence`), so hosts never re-invent the policy. `mode="always"` forces confirmation,
`"never"` skips it, `"auto"` compares `plan.confidence` with the threshold.

Deterministic and bilingual (English + Chinese briefs); unknown aspects become `open_questions`
instead of silent guesses. Column names stay `null` on purpose — the table does not exist yet.
Errors: `bad_parameter` (empty brief, unknown preset).

### 2.3c `ingest_paper` — D1, `needs_network`, M1/M2

```json
// request
{"source": "10.1099/mgen.0.000001", "min_quality": 0.0, "reproduce": true, "timeout_s": 900}
// response today
{"paper_id": "", "manifest_ids": [], "charts_found": 0, "reproduced": {},
 "not_implemented": true, "message": "paper ingestion lands with M1 …"}
```

`source` accepts a DOI, arXiv id, URL or absolute PDF path. When implemented it returns the created
`ChartReproManifest` ids so the host can immediately call `get_chart_manifest` /
`reproduce_chart_code` — service flow 2.

### 2.4 `search_chart_assets` — D1, ready (M3)

```json
// request
{"query": "phylogenetic tree enterotoxin", "k": 3}
// response (real brain, 7 ingested manifests)
{"assets": [{"asset_id": "pdf-958cda27/fig-2",
             "paper_title": "A novel staphylococcal enterotoxin SE02 …",
             "doi": "10.1016/j.ijfoodmicro.…", "chart_type": null,
             "reproduction_level": null, "visual_similarity": null,
             "thumb_path": "/abs/data/assets/pdf-958cda27/figures/fig-2.jpeg",
             "design_score": 0.45, "design_tier": "dense", "usefulness_score": 0.57}],
 "total": 1, "degraded": false, "message": ""}
```

Behaviour:

- Runs against **gbrain source `paper-kb`** (`federated=false`), page type `analysis`; the text is
  caption + citing paragraph + visual grammar + code summary, so a natural-language request matches.
- Frontmatter filters are pushed into gbrain (`--where chart_type=…`); level ordering and the preset
  filter are applied after retrieval, because gbrain only does equality.
- A **strict chart-type filter never hides a textual match**: if it returns nothing, the query is
  retried without it and the message says `no 'bar' asset matched; showing textual matches instead`.
- `schema_path` (optional) turns a table into a query: the table is profiled, a chart type and
  encoding are inferred, and the derived text/type drive retrieval, so `query` may be empty.
  `design_tier`, `has_code` and `dedupe` filter the result set; `render_sheet: true` writes a
  numbered contact sheet of the candidates and returns `sheet_path`.
- `query_image_path` (optional) switches to perceptual retrieval: the query and candidate thumbnails
  are fingerprinted with dHash (64-bit) and ranked by Hamming similarity (`image_similarity`, 0–1),
  with level/design/usefulness as tie-breakers. It is a *shape* signal, not a taste model: it finds
  figures that look alike, it does not judge them. Unreadable thumbnails simply do not rank.
- `degraded: true` only when the brain is disabled or unreachable — never because it is empty.
  `reproduction_level: null` means "not reproduced yet", which ranks below L1/L2/L3.
- `design_score` / `design_tier` come from the design judge (`docs/design-quality.md`); they are
  null when aesthetics has not been judged. Hosts can filter on `design_tier` (`gold`/`dense`).
- `usefulness_score` answers "is this the kind of figure worth reproducing" (venue, statistics,
  panel richness, caption completeness, verified code). Retrieval ranks by
  `reproduction_level`, then `0.7 × design_score + 0.3 × usefulness_score` (`[ranking]`), then text
  score.
- Assets are upserted by `gaxis kb ingest` (idempotent, hash-based) or automatically after
  `ingest_paper(mode="full")` when `[knowledge] auto_ingest = true`.

### 2.5 `get_chart_manifest` — D1, ready (M1)

```json
{"manifest_id": "pdf-958cda27/fig-3"}
→ {"manifest_id": "pdf-958cda27/fig-3", "found": true,
   "manifest": {"figure_ref": "Fig. 3", "chart_file": "assets/pdf-958cda27/figures/fig-3.jpeg",
                "caption": "Fig. 3. Effects of heat …", "citing_paragraph": "…",
                "chart_quality_score": 0.85, "geometry": {"page": 38, "pixel_width": 1000, …},
                "visual_grammar": {"chart_type": null, "notes": ["caption found on page 30",
                                   "artwork paired across pages …"]},
                "code_candidates": [], "reproduction": {"level": "none",
                                   "sandbox_run_status": "skipped"}}}
```

Paths are relative to the data root. `found: false` carries a message naming the next step
(`ingest_paper`).

### 2.6 `reproduce_chart_code` — D1, ready (M2), `cost: min`

On success the run is **assetized**: the script is copied to `data/assets/code/<asset>/<sha8>/`, the
manifest's last `code_candidate` points at that copy with `code_sha256`, and the KB page is refreshed
immediately (`sandbox_report.kb_refresh` says `refreshed`/`unchanged`/`failed: …`). `reproduction.data_source`
records `user` / `repo` / `synthetic` / `none`.

```json
// request
{"manifest_id": "pdf-958cda27/fig-3", "code_path": "/abs/figure.py",
 "data_path": "/abs/data.csv", "engine": "podman", "allow_network": false, "timeout_s": 300}
// response (abridged)
{
  "manifest_id": "pdf-958cda27/fig-3",
  "level": "L1", "run_status": "success", "visual_similarity": 1.0,
  "engine": "podman", "code_sha256": "…",
  "outputs": [{"path": "…/reproduced.png", "format": "png", "bytes": 8421}],
  "sandbox_report": {"engine": "podman", "image": "gaxis-repro:py312", "image_id": "4f1e703b3a28…",
                     "network": false, "network_enforced": true, "read_only_root": true,
                     "scan": {"findings": [], "licences": [], "blocking": false},
                     "dependencies": ["matplotlib"]},
  "similarity_detail": {"score": 1.0, "correlation": 1.0, "edge_agreement": 1.0, …},
  "manifest_path": "…/manifests/pdf-958cda27__fig-3.json"
}
```

Behaviour that matters:

- Runs in **rootless podman**: `--network none` unless `allow_network` *and* config permit it,
  read-only root, tmpfs `/tmp`, `--cap-drop ALL`, `no-new-privileges`, memory/CPU/pids caps.
- Static scan runs first: `os.system`/`subprocess`/`eval`/`exec`/`ctypes`/credential paths **block**
  the run (`level: "none"`, `run_status: "skipped"`, reason recorded); network use is a warning.
- Copyleft licences (GPL/AGPL) are refused — reuse the logic, not the code.
- `local` engine exists for development: it runs with the current interpreter and the report says
  `"network_enforced": false, "read_only_root": false, "warning": "no isolation"`.
- Grading: `similarity ≥ l1` (default 0.85) → L1; `≥ l2` (0.55) → L2; runs but below → L3; run
  fails → L3 with the stderr tail; blocked → `none`. Every level carries its reason in the manifest.
- The updated manifest is written back (`reproduction.*`, `code_candidates[]`), and a
  `reproduction.json` beside the run records scan, sandbox report and similarity components.
- Python only today; an `.R` script raises `unsupported_language` (an R image is a separate task).

Errors: `manifest_not_found`, `code_required`, `code_not_found`, `unsupported_language`,
`data_not_found`.

### 2.7 `adapt_chart_code` — D3, ready (KB templates)

```json
{"data_path": "/abs/path/results.tsv", "query": "bacterial growth curve with error bars",
 "asset_id": null, "preset": "asm", "backend": "python", "formats": ["pdf", "svg"], "dry_run": false}
→ {"figure_id": "line-…", "code_path": "…", "outputs": [...], "lint": {...},
   "source": "kb_asset", "asset_ids": ["a1b2…"], "fallback_reason": "", "not_implemented": false}
```

Resolution order:

1. `asset_id` — must be a **template** page (`type: template`). A paper figure asset is refused
   explicitly (`fallback_reason` says so); paper-code adaptation is not silently attempted.
2. Otherwise the exact template for `(preset, chart type, backend)`, where the chart type comes
   from `query` (`"grouped bar"`) or the data's inferred spec.
3. Otherwise builtin templates, with `fallback_reason` naming the missing template and the fix
   (`gaxis kb seed`).

A verified template is a real render produced by `gaxis kb seed`: emitted script, lint report and
manifest. Adaptation rewrites only the constants a human would edit — data path, output dir, stem,
delimiter, encoding intent — and leaves the plotting code untouched. Every rewrite is verified; an
unexpected template shape raises `adaptation_failed` instead of running the wrong code.
`dry_run: true` emits the script and manifest without executing it.

Templates are seeded locally (`gaxis kb seed`, ~2.5 min for 7 presets × 6 charts × 2 backends) and
live in the `paper-kb` source as `type: template` pages, so they never appear in
`search_chart_assets` (which queries `type: analysis`).

### 2.8 `compose_panels` — D3, ready

```json
{"panel_ids": ["bar-…", "line-…"], "preset": "nature_microbiology", "layout": "1x2",
 "width_mm": null, "height_mm": null, "labels": true, "out_dir": null}
→ {"composition_id": "composition-…", "panels": [{"manifest_id": "bar-…", "label": "A", "code_sha256": "…"}],
   "layout": [1, 2], "output_pdf": "…", "output_png": "…", "lint": {...}}
```

`uniform: true` re-renders each panel from its manifest at the composition preset and cell size
before placement, so typography is consistent; the default places the existing PDFs untouched.

Places finished **PDF** panels on one page with PyMuPDF (vector preserved, nothing re-rendered),
adds A/B/C letters, and records each panel's `code_sha256` in the composition manifest. Panel ids are
the ids printed by `render_chart_from_data`, or a path to a panel's `manifest.json`; the same runs through the CLI
(`gaxis compose --panels a,b`). A panel without a PDF output is refused with `panel_not_vector`
rather than being rasterised silently; too-small layouts raise `bad_layout`.

### 2.9 `list_figure_recipes` — D1, ready

```json
// request
{"chart_type": "network"}
// response
{"recipes": [{"recipe_id": "amr-network", "title": "AMR co-occurrence network",
              "chart_type": "network", "x": "source", "y": "target", "weight": "weight",
              "preset": "asm", "required_columns": ["source", "target", "weight"],
              "optional_columns": ["source_class", "target_class"]}], "total": 1}
```

Curated table→figure contracts from `style/figure_recipes.toml`. A recipe binds columns and a
preset; it never computes analysis. Available: `amr-network`, `amr-prevalence-bar`, `snp-tree`.

### 2.10 `render_figure_recipe` — D3, ready

```json
// request
{"recipe_id": "amr-network", "data_path": "/abs/edges.csv", "preset": "asm",
 "color_map": {"beta-lactam": "#E69F00"}, "run_analysis": false,
 "analysis_params": {"min_prevalence": 0.2}, "dry_run": false}
// response
{"recipe_id": "amr-network", "figure_id": "network-…", "code_path": "…",
 "outputs": [...], "lint": {...}, "manifest": {"recipe_id": "amr-network", ...},
 "source": "figure_recipe", "not_implemented": false}
```

Checks the recipe's required columns first (`recipe_contract_violation` names the missing ones),
then renders with the recipe's encodings/preset. The manifest records `recipe_id` and
`source: figure_recipe`. With `run_analysis: true`, `data_path` is treated as the analysis input
(e.g. `sample,gene,gene_class`), the recipe's analysis runs first, and `analysis_run_id` is
recorded. `dry_run` writes the script/manifest without executing it.

## 3. Result conventions

- Structured output; hosts that want JSON strings stringify at the adapter boundary.
- Every failure is `{"code", "message", "hint?"}` with a stable code.
- Paths in responses are absolute and readable by the calling process.
- `outputs[]` geometry is measured from the artifact, not assumed from the preset.
- `lint.issues[]` uses the numeric `L0xx` codes documented in `docs/presets.md`.

## 4. Versioning

| Contract | Date | Change |
|---|---|---|
| v1.0 | plan v2.0 | `search_chart_assets`, `get_chart_manifest`, `reproduce_chart_code`, `adapt_chart_code`, `health` |
| v1.1 | M0 scaffold | + `describe_data_schema`, `render_chart_from_data` (ADR-14); gating metadata on all tools; `adapt_chart_code` ships with a builtin-template fallback |
| v1.2 | service flows | + `plan_chart_from_brief` (data-free planning) and `ingest_paper` (on-demand paper ingestion); see `docs/service-flows.md` (ADR-17) |
| v1.3 | flow 2 refinement | `ingest_paper` gains `mode` (kb_first/full) plus source classification and dedup ids; `plan_chart_from_brief` gains the configured confirmation policy (ADR-19/20) |
| v1.4 | M2 reproduction | `reproduce_chart_code` real: `data_path`, `engine`, `code_sha256`, `sandbox_report`, `similarity_detail`, `manifest_path` |
| v1.5 | M1 completion | identifier resolution (Crossref/arXiv/PubMed/PMC/Unpaywall), PDF download, repository link + plotting-script discovery; ingest result gains `pdf_url`, `repository_urls`, `code_candidate_count`, request gains `with_code` |
| v1.7 | design tiering | `ChartAssetSummary` gains `design_score` and `design_tier` (gold/dense/reject) |
| v1.8 | usefulness | `ChartAssetSummary` gains `usefulness_score`; retrieval ranks by design × usefulness |
| v2.8 | recipe analysis | `render_figure_recipe` can run the recipe's analysis (`run_analysis`, `analysis_params`); manifest records `analysis_run_id` |
| v2.7 | rotated labels | `RenderRequest.rotate_labels` (x tick angle 0–90) |
| v2.6 | figure recipes | + `list_figure_recipes`, `render_figure_recipe` (curated table→figure contracts) |
| v2.5 | shared palette | `RenderRequest.color_map` (category → hex) for consistent annotation/node colours |
| v2.4 | tree annotations | `RenderRequest.annotations` (multiple tip annotation columns) |
| v2.3 | tree chart | `ChartType` gains `tree` (Newick edges → rectangular cladogram, both backends) |
| v2.2 | network chart | `render_chart_from_data` gains `weight`; `ChartType` gains `network` (circular edge layout, both backends) |
| v2.1 | schema search + batch | `search_chart_assets` accepts `schema_path`, `design_tier`, `has_code`, `dedupe`, `render_sheet` (returns `sheet_path`); `ChartAssetSummary.has_code`; `ReproduceChartCodeResult` reports KB refresh in `sandbox_report.kb_refresh`; `RenderRequest.source_asset` records selection feedback |
| v2.0 | perceptual + uniform | `search_chart_assets` gains optional `query_image_path` and `image_similarity` (dHash ranking); `compose_panels` gains `uniform` (re-render panels at the composition preset) |
| v1.9 | composition + adaptation | new `compose_panels` tool; `adapt_chart_code` now retrieves verified KB templates and reports `fallback_reason` instead of degrading silently |

A breaking change requires: version bump, snapshot refresh, `docs/mcp-tools.md` update, and a note
in `CHANGELOG.md`.
