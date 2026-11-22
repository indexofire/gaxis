# DESIGN.md — gaxis architecture

Status: living document, tracks the code as it lands. Product plan lives in `dev/plan.md`
(v2.0, intentionally uncommitted); rules for contributors live in `AGENTS.md`.

## 1. Framing

gaxis exists to answer two questions with one engine:

1. **bacmap / agent path** — "what does the literature look like for this figure, and can I reuse
   that code?" → retrieve paper figure assets, validate their code, adapt it to local data.
2. **standalone path** — "here is my table, give me a figure a journal will accept, and give me the
   code so I can defend and edit it."

Both are the same deterministic pipeline: `ChartSpec → script → sandboxed run → figure → lint →
manifest`. Paper knowledge only widens the *source of the script*; it is never a precondition.

Consequence: M0 is useful on day one, with an empty knowledge base. Plan v2's original ordering
(KB first) would have made the tool useless until M3.

## 1b. The two service flows (product core)

The plan's modules are the machinery; these are what they are for. Full detail:
`docs/service-flows.md`.

1. **Natural language → cases → dialogue → plan/data/code.** `plan_chart_from_brief` produces a
   data-free `ChartPlan` (spec draft, required column roles, style notes, open questions,
   confidence), the host LLM converges with the user, then `describe_data_schema` +
   `adapt_chart_code`/`render_chart_from_data` deliver figure + script + manifest.
2. **Paper in → similar figure out.** `ingest_paper` → `get_chart_manifest` →
   `reproduce_chart_code` → `search_chart_assets` → `adapt_chart_code` to the user's own data.

Background crawling (modules A–D, H) exists only to stock the knowledge base these two flows read.

## 2. Topology

```
clients:  bacmap (primary) | DSH | Pi | Hermes | CLI | notebook
              │  MCP Streamable HTTP (+ bearer token), or in-process CLI import
              ▼
host adapters (thin, ≤150 lines, no shared imports)
              ▼
kernel: src/gaxis/service.py  (ten tools, transport-neutral; adapt/compose/ops in siblings)
   ├── models/   pydantic contracts (ChartSpec, DataSchema, FigureManifest, lint, tool I/O)
   ├── spec/     inference
   ├── style/    journal presets, palettes, rcParams, publication lint
   ├── render/   emit.py + templates (matplotlib, ggplot2)
   ├── exec/     script execution (local now, podman sandbox at M2)
   ├── acquire/ parse/ repro/ sandbox/          ← M1–M2 (paper side)
   ├── kb/       gbrain paper-kb + asset store + verified templates  ← M3
   ├── adapt.py  template -> local data (verified constant rebinding)
   ├── compose.py multi-panel vector composition
   └── ops/      checkpointed ingestion queue (SQLite)  ← M6 seed
```

Three script producers, one render path:

```
builtin templates  ─┐
KB asset (L1/L2)   ─┼─► ChartSpec ─► emit ─► run ─► fig + lint ─► manifest
paper reproduction ─┘        (source=builtin_templates | kb_asset | paper_reproduction)
```

`source` is recorded in every manifest, so a figure always states where its code came from.

## 3. Decisions (ADRs)

Inherited from plan v2 (keep the numbering) plus the ones this implementation adds.

| ID | Decision | Why |
|---|---|---|
| ADR-01 | Independent MCP server, not embedded in bacmap | bacmap is a deterministic analysis engine; core assets must not be locked to one host |
| ADR-02 | Streamable HTTP for production; stdio only for debugging | stdio binds process lifetime to the host; multi-client and on-demand use need HTTP |
| ADR-03 | Hosts get thin adapters, not the kernel | kernel survives host churn |
| ADR-04 | gbrain single instance, `paper-kb` with `federated=false` | paper-figure semantics pollute other corpora |
| ADR-05 | Frozen MCP tool contract; host differences live in adapters | new host = new adapter, kernel untouched |
| ADR-06 | Paper code must pass sandbox run + visual compare before entering the KB | unverified code is a liability |
| ADR-07 | Acquisition/reproduction on a timer, not resident | freshness matters, continuous compute does not |
| ADR-08 | Every artifact carries source asset ids and input hashes | auditability |
| ADR-09 | Strong-pair / weak-link / confidence tiers | perfect automatic alignment is unattainable |
| ADR-10 | Low reproduction levels are indexed but down-weighted, with reasons | style templates still have value |
| **ADR-11** | **Sandbox is rootless podman** | user decision; available on this machine; no daemon, no root, image-pinned environments |
| **ADR-12** | **R/ggplot2 is a first-class backend from M0** | the target users publish R figures; "Python only" would exclude half the corpus |
| **ADR-13** | **`ChartSpec` is the only IR between producers and renderers** | prevents "generate" and "adapt paper code" drifting into two engines |
| **ADR-14** | **Contract grows from 5 to 7 tools** (`describe_data_schema`, `render_chart_from_data`) | a data-in/figure-out call is not an "adaptation"; overloading `adapt_chart_code` would hide intent from hosts and from data-class gating |
| **ADR-15** | **Publication lint is file-level, not backend-level** | one rule set can judge matplotlib PDFs and cairo_pdf PDFs identically |
| **ADR-16** | **Journal presets are TOML data, not code** | microbiology journals share geometry; adding a journal must not touch templates |
| **ADR-17** | **The contract serves two flows, not two engines**: a data-free planning tool (`plan_chart_from_brief`) and an on-demand paper ingest (`ingest_paper`) | flow 1 must converge before data exists, so it cannot be expressed by `render_*`; flow 2 needs a paper entry point, and periodic crawling alone makes the tool feel stale |
| **ADR-18** | **Planning is deterministic and bilingual; judgement stays with the host LLM** | a plan must be explainable field by field (ADR-08), and "is this paper's figure worth copying" is a judgement, not a kernel decision |
| **ADR-19** | **Paper ingestion is knowledge-base first** (`mode="kb_first"` is the default; deep parsing is opt-in) | showing existing assets is seconds, parsing+reproducing is minutes; the user should not pay for the expensive path before seeing the cheap one |
| **ADR-20** | **Confirmation policy lives in configuration** (`[confirmation] mode/min_confidence`), and the plan carries the verdict | hosts must not implement their own thresholds; the kernel computes `requires_confirmation` so behaviour is auditable |
| **ADR-22** | **Grading is an explainable metric plus a reason, never a bare label** | a level decides whether code may be reused; the manifest stores the sandbox report, similarity components and the branch that produced the level |
| **ADR-23** | **Two sandbox engines, one port** (`podman` production, `local` development) | tests and laptops cannot always build an image, but a local run must announce that it enforces no isolation |
| **ADR-21** | **Panels are composed after the fact, from panel scripts, not re-rendered** | users finish single panels first; `GAXIS_PANEL_SOURCE=1` makes an emitted script sourceable (patchwork/cowplot/subfigure) and keeps vector output, with child manifests preserving the evidence chain |

## 4. The pipeline in detail (implemented)

### 4.0 `ChartPlan` (service flow 1, `spec/brief.py`)

A brief becomes a `ChartPlan`: chart type, journal preset, palette, backend, `required_columns`
(role/kind/hint), `style_notes`, `open_questions`, `confidence`. Keyword tables are bilingual
(EN + 中文) and ordered so "stacked bar" beats "bar". Nothing is guessed silently: anything the
text does not state becomes a question. `x/y/hue` stay `null` because no table exists yet — the
host asks the user, then renders.

### 4.1 `DataSchema` (`models/schema.py`)

### 4.0b Paper parsing (M1, `parse/pdf.py`)

`parse_pdf` walks text **lines**, not blocks: real PDFs merge the caption into a body block, so
block-level matching finds nothing. Captions are recognised by label + delimiter (or a capitalised /
CJK continuation — "Fig. 2 in a companion paper" is a citation, not a caption), then merged while the
font size and column stay constant; margin line-numbers are skipped rather than ending the caption.

Artwork comes from three sources, in order: embedded image XObjects (with a size/page-area filter to
drop logos), a vector band between the last long text line and the caption (checked for *visible* ink
so watermarks and white knockout glyphs do not count), and cross-page pairing for pre-proof layouts
where all artwork sits in a separate section (`artwork paired across pages`). If no artwork exists,
the figure is recorded as **caption-only** (`chart_file=""`, low quality, explicit note) — fabricating
a crop of body text would poison retrieval. Quality score weights caption, artwork size/area, vector
originality and whether the body text cites the figure.

**Beyond a local PDF (M1 completion).** `acquire/metadata.py` resolves DOI (Crossref + Unpaywall),
arXiv (Atom API), PubMed (E-utilities) and PMC (OA service) to metadata plus an open-access PDF URL;
`acquire/download.py` fetches it with a User-Agent, a size cap, a `%PDF` magic check and atomic
writes. `acquire/repo.py` then finds repository links in the paper text (GitHub/GitLab/Bitbucket/
Zenodo, issue/blob URLs filtered out), shallow-clones them (`--depth 1 --filter=blob:limit=1m`,
size-capped) and scores plotting scripts by filename + plotting evidence, attaching them to the
manifests as `code_candidates` with licence, language and dependency hints. Cloned code is never
executed here — reproduction stays behind `reproduce_chart_code` and the sandbox.

Persisted layout: `assets/pdf-<sha8>/source.pdf`, `assets/pdf-<sha8>/figures/fig-<n>.<ext>`,
`manifests/pdf-<sha8>__fig-<n>.json`; paths inside manifests are relative to the data root.

### 4.1 Data profile

CSV/TSV → column profiles: `kind` (`numeric|categorical|datetime|boolean|unknown`),
`n_unique`, `missing_ratio`, `sample_values`, `unit_hint` (bracket or known unit token: FPKM, TPM,
mm, h, …), file `sha256`, detected delimiter. `summary_markdown()` is the LLM-facing view used by
hosts.

### 4.2 `ChartSpec` (`models/spec.py`)

Fields: `chart_type` (`bar|stacked_bar|line|scatter|box|heatmap`), `x`, `y`, `hue`, `yerr`, labels,
`preset`, `palette`, `backend` (`python|r`), `width_mm`, `height_mm`, `dpi`, `formats`,
`annotate_values`. `extra="forbid"` so typos surface immediately.

Inference (`spec/infer.py`) rules that matter:

- categorical columns with `n_unique == n_rows` are treated as IDs and skipped;
- x = the factor with **more** levels, hue = the factor with **fewer** (≤ 8) — a 12-colour legend is
  a defect, not a feature;
- a numeric measure always beats row counts; counts are the last resort;
- numeric x + numeric y → scatter; categorical x with > 12 levels → box; otherwise grouped bar.

### 4.3 Script emission (`render/emit.py` + `render/templates/`)

`templates/python_header.tpl` + `python_<chart>.tpl`, and `r_header.tpl` + `r_<chart>.tpl`, assembled
by `@PLACEHOLDER@` substitution. The emitted script:

- hardcodes the rcParams/theme derived from the preset (so it is portable);
- carries the data path, output dir and column mapping in one obvious place;
- aggregates identically in both backends (`summarise_groups`: mean + SD, or mean of a supplied
  `yerr` column) so matplotlib and ggplot2 figures are statistically comparable;
- never imports gaxis.

If `y` is absent, both backends switch to count mode.

**Stroke parity (measured, not assumed).** ggplot2 interprets `linewidth` in lwd units (1/96 inch),
which renders ~2.13× heavier than the same value in points; a 1.0 linewidth stroke measured 2.16 pt
(agg_png, 600 dpi) versus 0.96 pt from matplotlib. The R header therefore converts preset point
values through `pt_to_lwd()`, so a `nature_microbiology` bar chart carries the same stroke weight in
both backends. `figure_id` includes `PIPELINE_VERSION` so a template change cannot leave stale
figure directories masquerading as current output.

### 4.4 Execution (`exec/runner.py`)

`run_script(script, cwd, timeout_s, backend)` → `ExecResult(returncode, stdout, stderr, duration_s)`.
Environment is pinned: `MPLBACKEND=Agg`, `LC_ALL=C.UTF-8`, single-threaded BLAS, fixed
`PYTHONHASHSEED`. Timeout returns `returncode=-9`. A full log is written next to the figure as
`render.log`.

### 4.5 Lint (`style/lint.py`) — the measurable form of "publication grade"

| Code | Severity | Check |
|---|---|---|
| L001 | error | declared output file missing/empty |
| L002 | error | no vector output while the preset requires one |
| L003 | error/info | raster DPI below 300 (error) or below preset DPI (info) |
| L004 | error | PDF contains Type 3 fonts (journals reject them) |
| L005 | warning | rendered font ≠ preset font (silent fallback detection) |
| L006 | error/info | geometry deviates > 15% (error) / > 3% (info) from journal width/height |
| L007 | warning | palette is not colour-blind safe |
| L008 | warning | declared title/axis label absent from the SVG text layer |
| L009 | warning | file < 2 KB (blank figure) |

PDF inspection inflates FlateDecode streams before looking for `/MediaBox` and `/Type3`, because
cairo (ggplot2's `cairo_pdf`) compresses them. PNG DPI comes from the `pHYs` chunk; SVG width/height
and text come from the XML. This is why the rule set is backend agnostic (ADR-15).

### 4.6 Manifest (`models/manifest.py`)

`figure_id, created_at, spec, data (full DataSchema incl. sha256), preset, backend, style, code_path,
code_sha256, outputs[{path,format,bytes,width_mm,height_mm,dpi}], lint, source, asset_ids,
generator`. Written as `manifest.json` inside the figure directory; it is the unit the KB will
ingest at M3.

## 5. Journal presets (microbiology first)

TOML in `src/gaxis/style/journal_presets/`: `default`, `nature`, `nature_microbiology`, `asm`
(mBio/AEM/Microbiology Spectrum), `isme` (ISME J), `cell_host_microbe` (Cell Press),
`microbial_genomics` (Microbiology Society). Fields: single/double width, heights, base/label/title
pt, line/spine widths, marker size, DPI, font family chain, palette, legend frame, grid, spines,
`vector_required`. Adding a journal = adding a TOML file, no code change (ADR-16). Details:
`docs/presets.md`.

Fonts resolve through `matplotlib.font_manager` with an explicit fallback chain
(Arial → Helvetica → Liberation Sans → Nimbus Sans → DejaVu Sans). On this workstation
Liberation Sans is the resolved metric-compatible Arial substitute; if a fallback happens, lint
L005 reports it.

## 6. Tool contract v2.1

Ten tools, all declared in `models/tools.py` with exported JSON Schemas, data class, side effects,
network need, cost and milestone. Reference: `docs/mcp-tools.md`. Frozen by
`tests/contract_snapshot.json`.

| Tool | Data class | State |
|---|---|---|
| `health` | D1 | ready |
| `describe_data_schema` | D3 (follows input) | ready |
| `render_chart_from_data` | D3 (follows input) | ready |
| `search_chart_assets` | D1 | ready (M3): gbrain paper-kb, text + metadata filters |
| `get_chart_manifest` | D1 | ready (M1) |
| `reproduce_chart_code` | D1 | ready (M2): podman sandbox + similarity grading |
| `adapt_chart_code` | D3 | ready: verified KB template → rebind → run; explicit fallback |
| `compose_panels` | D3 | ready: vector composition, composition manifest |
| `plan_chart_from_brief` | D1 | ready (heuristics; KB cases at M3) |
| `ingest_paper` | D1 | PDF ingest ready (M1); DOI resolution M1, reproduction M2 |

Hosts use the metadata for **pre-execution** gating: bacmap's `cloud` profile (ceiling D1/D2) must
never see a D3/D4 call at all, not discover it at runtime.

## 7. bacmap integration

`gaxis.client` (168 lines, async, one connection, seven typed calls) and
`src/gaxis/mcp/{server,http}.py` are implemented and covered by tests that spawn a real
Streamable-HTTP server on loopback (`tests/test_mcp.py`). The bacmap side holds one adapter,
`integrations/bacmap_upstream_gaxis.py` (143 lines, tested by `tests/test_bacmap_upstream.py`), that:

1. connects to `http://127.0.0.1:8770/mcp` with a bearer token;
2. filters tools by the active bacmap profile and data class;
3. renames them `bacmap_chart_*` and converts structured results to bacmap's JSON-string habit;
4. never caches business results (reproduction is expensive; caching belongs to the KB).

Two details worth remembering:

- **Fail-closed gating is doubled**: invisible at registration (the D3 tools are never added under a
  D1 profile) *and* rejected at call time, mirroring bacmap's own legacy-tool pattern.
- **`params` nesting**: because bacmap's tool convention is one `params` object, the adapter builds a
  pydantic input model per tool from `TOOL_SPECS[...].input_schema` and annotates the handler at
  runtime. Schemas therefore stay generated from the frozen contract instead of hand-written.
- A TCP preflight runs before the MCP handshake, so "gaxis is not running" returns an immediate JSON
  error instead of surfacing inside anyio teardown.

Neither repository imports the other at runtime except through MCP and the client package.

## 8. Sandbox (M2, podman per ADR-11)

`exec/runner.py` is the seam. The podman implementation will:

- run `podman run --rm --network=none --read-only --tmpfs /tmp:size=512m`
  `--memory=4g --cpus=2 --pids-limit=256 --security-opt=no-new-privileges`
  `-v <asset>:/work:rw -v <data>:/data:ro` with an image pinned by digest;
- mount no home directory, no docker socket, no host `/etc`;
- run a static scan (dangerous imports/calls, outbound sockets, writes outside `/work`) and a
  licence check (GPL-family → rewrite the logic, do not copy) before execution;
- return `ExecResult` plus a `sandbox_report` recorded in the manifest.

Acceptance (plan §4 D): zero escapes, licence interception ≥ 95%.

## 9. Knowledge base (M3, gbrain)

- **Asset store**: `data/assets/<asset_id>/` → original figure, manifest, code, environment lock,
  render output, comparison report.
- **Vectors**: figure image embedding (CLIP-style), caption/citing-paragraph text embedding, code
  semantic embedding — three indexes, queried in parallel.
- **Graph**: paper → figure → code candidate → dependency → input schema → reproduction level →
  visual grammar.
- **gbrain**: register `paper-kb` with `federated=false` (ADR-04). Retrieval weight =
  f(reproduction level, visual similarity, lint cleanliness, human feedback), so L3 assets remain
  searchable but never outrank verified L1 code (ADR-10).

gbrain **0.60.740.0** is now installed and verified in this environment (`pixi run gbrain-install`
/ `gbrain-init`; brain in `$XDG_DATA_HOME/gaxis/gbrain`, outside the worktree). ADR-04 holds
literally: `sources add paper-kb --no-federated` produces a source that "is only searched when
explicitly named via `--source`". Writes go through revision-guarded `put` with
`--content-origin tool_output`; reads go through `search --source-id paper-kb --where <frontmatter>`
(`chart_type`, `reproduction_level`, …). `sync` is unusable here (it demands git/writer-coordinator
ownership of a canonical worktree), so gaxis ingests pages explicitly and treats the brain as a
**derived, rebuildable index** while manifests stay authoritative.

Images are files, not vectors: pages carry `image_path` and a `visual_grammar` text block, so a
multimodal host opens the image itself and text search still matches visual intent. Retrieval *by
image* would need an image embedding space; two paths are documented (local CLIP, or gbrain's
`voyage:voyage-multimodal-3`), both behind a `VisualIndex` port. Details and evidence:
`docs/gbrain-integration.md`.

## 9b. Configuration (`gaxis.toml`)

One typed config (`config.GaxisConfig`), loaded from `--config` > `$GAXIS_CONFIG` >
`./gaxis.toml` > `~/.config/gaxis/config.toml`, then overridden by a small set of `GAXIS_*` env
vars. Tables: `[confirmation]` (mode + threshold), `[render]` (timeout, default preset/backend),
`[ingest]` (kb_first default, network permission, timeouts, min quality), `[knowledge]` (gbrain
source, gbrain home, timeouts). Invalid configuration raises `config_invalid` — no silent fallback,
because a wrong threshold silently rendering figures is worse than a hard failure.

## 9c. Panel composition (M4, implemented)

Panels are ordinary figures with their own manifest. Composition arranges the finished **PDF**
pages with PyMuPDF, so vector content survives and nothing is re-drawn:

```
compose_panels(panels=[figure_id…], layout="2x2", preset=…) -> CompositionManifest
  panels: [{manifest_id, label, code_sha256}], layout, width_mm/height_mm, lint
```

`--uniform` re-renders each panel first from its own manifest at the composition preset and the
cell size, so type sizes and line weights match; without it, panels are placed as rendered.
PNG-only panels are refused (`panel_not_vector`) rather than rasterised silently. Both backends
also honour `GAXIS_PANEL_SOURCE=1`, which builds the figure object without saving, for hosts that
want patchwork-style layout instead of page placement.

## 9d. Reproduction sandbox (M2, implemented)

`repro/runner.py` orchestrates: static scan → sandbox run → raster comparison → grading →
manifest update. `sandbox/` holds the port (`base.py`), the podman engine, the local engine, the
reproduction image builder and the scanner.

- **Image (python)**: `gaxis-repro:py312` built once from a pinned `python:3.12-slim` plus
  `matplotlib==3.11.2 numpy==2.5.5` (`sandbox/image.py`, `[sandbox] autobuild`); the resolved image
  id is recorded in every report, so a later library change cannot silently move a grade.
- **Isolation**: `--network none`, `--read-only` root + tmpfs `/tmp`, `--cap-drop ALL`,
  `no-new-privileges`, memory/CPU/pids limits, work dir mounted rw, input data mounted read-only at
  `/data`. Tests verify network blocking and read-only root from inside the container.
- **Scan**: critical findings block (`shell_exec`, `subprocess`, `eval_exec`, `ctypes`,
  credential paths, destructive fs); network/absolute-write/pickle are warnings. GPL/AGPL refuse
  reuse. Blocking is a recorded outcome, not an exception.
- **Comparison**: 256×256 grayscale, weights 0.50 correlation + 0.25 (1−MAD) + 0.15 edge agreement +
  0.10 ink agreement, multiplied by an aspect-ratio penalty. Components are stored.
- **Grading**: L1 ≥ 0.85, L2 ≥ 0.55, otherwise L3; failed runs are L3 with a stderr tail; blocked
  runs are `none`. Thresholds are configuration (`[reproduction]`), not constants.
- **Image (R)**: `gaxis-repro-r:4.5` built from `rocker/tidyverse:4.5` plus `svglite`,
  `patchwork`, `cowplot` from CRAN; `.R`/`.Rmd` scripts run with `Rscript` in that image and the
  report records which image was used.
- **Quality calibration** (`quality.py`, `gaxis quality sheet|calibrate`): the extraction score is six
  components with configurable weights; a human ranking of 20–30 figures drives a coordinate-descent
  fit (Spearman, ties handled). Acceptance: ρ ≥ 0.7 between score order and human order.
- **Artifacts**: `data/repro/<manifest>__<fig>/<code_sha8>/` with the script, outputs,
  `reproduction.json`; the manifest gains `code_candidates[]` and `reproduction.*`.

Verified end to end: a 43-page paper's manifest reproduced in podman with `similarity 1.0`, level
L1, image id recorded, network disabled.

## 9e. Knowledge base ingestion and retrieval (M3, implemented)

`kb/` is a thin projection of the manifests onto gbrain:

- **pages.py** — `ChartReproManifest` → markdown page (`type: analysis`). Frontmatter carries the
  filterable facts (`chart_type`, `reproduction_level`, `sandbox_run_status`, `visual_similarity`,
  `image_path`, `code_path`, `doi`, `asset_id`); the body carries caption, citing paragraph, visual
  grammar (with EN/中文 chart synonyms) and reproduction state. Pages are **derived and rebuildable**;
  manifests stay authoritative.
- **ingest.py** — hash-based idempotency with state in `data/kb/state.json`; unchanged assets are
  skipped, a re-validated asset (L2 → L1) produces a new hash and rewrites its page; `--force`
  rewrites deliberately. Ingestion runs automatically after `ingest_paper(mode="full")`.
- **search.py** — gbrain returns chunk hits; we collapse to one hit per page, read frontmatter, apply
  level/preset filters locally, and rank by (reproduction level, text score). A strict chart-type
  filter that yields nothing is retried without the filter and the message says so.
- **gbrain.py** — subprocess CLI adapter (`put/get/delete/search/call get_health`) with timeouts and
  typed `KbError`; unreachable brain degrades `search_chart_assets` to `degraded: true`.
- Lifecycle: ingest → `reproduce_chart_code` → re-ingest (the level changes the page hash and the
  ranking). Fresh M1 manifests have `reproduction_level: none`, so they are searchable but rank last
  until reproduced — intentional (ADR-10).

Test isolation is a rule, not a courtesy: an autouse fixture disables the knowledge base, so a test
can never write into a developer's real brain.

## 10. Milestones and where the acceptance criteria live

| Phase | Deliverable | Status | Acceptance (plan §8) |
|---|---|---|---|
| **M0** | deterministic render pipeline + lint + manifest + CLI + MCP server/client/adapter | **done**: 7 chart types × 2 backends × 7 presets lint-clean; contract v2.2 frozen | 36/36 lint-clean; review accepted |
| **M1** | paper acquisition, figure/caption/code extraction, `ChartReproManifest` | **done**: identifiers, bounded download, repo discovery, manifests | completeness/pairing measured per corpus, not yet a single number |
| **M2** | podman sandbox, comparison, L1/L2/L3 | **done**: rootless podman, similarity decomposition, code assetisation | success/agreement depend on paper code availability |
| **M3** | asset store, gbrain `paper-kb`, retrieval | **done**: pages, embeddings, text/schema/image retrieval | Top-5 measured by the owner on real queries |
| **M4** | adaptation, trial run, composition | **done**: `kb seed`, `kb adopt`, `adapt`, `compose` (+`--uniform`) | first-run success depends on template coverage |
| **M5** | host adapters | **partial**: CLI + bacmap reference adapter; Pi/DSH/Hermes pending | adapters ≤150 lines |
| **M6** | scheduling, checkpoints, self-healing | **partial**: SQLite queue, retries, stall reclaim, heartbeat, `ops verify`; layered checks pending | stall detection, restart saving, false positives |


M0 completion gates: `pixi run check` green, `gaxis render` works for both backends, and the
contract snapshot test passes.

## 11. Testing strategy

- Unit: schema inference, spec inference, preset loading, rcParam validity, lint parse helpers.
- E2E per backend: render → lint clean → geometry within tolerance → rerun the emitted script
  standalone (proves it is self-contained).
- Every chart type is parametrized in tests; adding a type without a test is a review-blocking bug.
- Contract tests: names frozen, gating metadata present, JSON snapshot unchanged.
- Transport tests: real server on loopback, bearer auth enforced (401 without token, refusal to
  start without one), describe/render round trip, stable error codes, stub degradation.
- Host-adapter tests: profile filtering, `bacmap_chart_*` naming, schema fidelity, gated calls
  rejected before the network, JSON-string results.
- Human review (not CI): `pixi run review` renders 6 charts x 3 presets x 2 backends, writes
  `data/review/REVIEW.md` and a contact sheet. This is the acceptance gate for the standalone
  experience before the paper-side milestones start.
- R tests skip with a clear reason if `Rscript` is absent, never silently pass.

## 12. Open questions

1. Multi-panel composition (A/B/C panels): part of M4 output format, or a separate `compose_panels`
   tool? Current contract has no panel tool.
2. TIFF output: implemented in both backends but unverified against a journal's CMYK requirement.
3. gbrain endpoint and auth model; SQLite fallback may become permanent for single-user installs.
4. Whether `describe_data_schema` should also accept embedded CSV text (agent-friendly) — today it
   takes an absolute path only, which keeps data classes honest.
