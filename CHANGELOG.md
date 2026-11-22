# Changelog

Format: keep-a-changelog-ish. Versions follow `pyproject.toml`.

## [Unreleased]

### Added

- **LLM reconstruction fallback** (`gaxis reconstruct`, `reproduce-paper --reconstruct-missing`): for
  figures whose author code is missing or broken, a vision model writes a script; the same sandbox
  runs it, the same comparator grades it, and a revision loop feeds the render plus similarity
  components back. Provenance is explicit: `reproduction.method = llm_reconstruction` / `llm_repair`,
  generated code candidates carry `generated: true`, and retrieval ranks author reproductions first
  at the same level. A generation that never runs is graded `none` and is not added as a candidate;
  a repair that leaves the author script unchanged stays `method = author_code`.
- `[reconstruct]` configuration (inherits `[design]` base_url/key when empty), default model
  **`glm-5.3-flash`** with hidden thinking disabled and a `fallback_model` (`glm-4.5v`) used only
  when the primary stays below L2; `reconstruct --model/--timeout/--max-side` overrides, and
  deterministic repairs for common model mistakes (missing `import matplotlib`, `plt.use`, raw
  newlines inside string literals). Each run is timestamped (`data/recon/<fig>/<run-id>/`) with
  per-round `attempt.json`, a run-level `reconstruction.json`, and no cross-run overwrites.

### Fixed

- Repository discovery from PDFs: URLs wrapped across lines or split at spaces
  (`https://github. com/owner/repo`) are rejoined before matching; local PDF ingestion now runs
  code discovery too (it previously only ran for DOI/URL sources).

## [0.1.0] — 2026-11-21

First working line: extraction + reproduction + knowledge base + design judge.

### M0 — deterministic figure pipeline, presets, lint, contract

### Added

- **Deterministic figure pipeline**: `DataSchema` profiling → `ChartSpec` inference → standalone
  script emission → subprocess run → publication lint → `manifest.json` with `data.sha256` and
  `code_sha256`.
- **Six chart types** (bar, stacked bar, line, scatter, box, heatmap) in **two backends**:
  matplotlib (`figure.py`) and ggplot2 (`figure.R`). Both aggregate identically (mean + SD, or a
  supplied `yerr` column) and support a count mode when no numeric `y` is given.
- **Seven microbiology-first journal presets** as TOML data: `default`, `nature`,
  `nature_microbiology`, `asm` (mBio/AEM), `isme`, `cell_host_microbe`, `microbial_genomics` —
  geometry in mm, type in pt, resolved font chain, vector font safety.
- **Publication lint** (`L001`–`L009`) operating on finished files, so it judges matplotlib and
  ggplot2 output by the same rules: vector presence, DPI, Type 3 fonts, geometry deviation, font
  fallback, colour-blind safety, missing labels.
- **Five colour palettes**, colour-blind safe default (`okabe_ito`).
- **MCP tool contract v2.1** with ten tools and per-tool gating metadata
  (`data_class`, `side_effects`, `needs_network`, `cost`), frozen by `tests/contract_snapshot.json`.
- **MCP server** (`gaxis-mcp`): Streamable HTTP with mandatory bearer token, DNS-rebinding
  protection, security headers and fail-closed auth; stdio for debugging only. All ten contract
  tools registered, hand-written signatures, no schema drift.
- **Typed client** `gaxis.client.GaxisClient`: one connection, seven async calls, kernel error
  payloads raised as `GaxisError`.
- **bacmap reference adapter** `integrations/bacmap_upstream_gaxis.py` (143 lines): registers
  `bacmap_chart_*` tools with data-class gating at registration *and* call time, JSON-string
  results, TCP preflight; covered by tests against a live server.
- **`adapt_chart_code` is usable now** in degraded form: renders with builtin templates and reports
  `fallback_reason`; `dry_run` emits code + manifest without executing.
- **CLI**: `render`, `describe`, `presets`, `palettes`, `lint`, `tools`, `health`, `version`.
- **Backend stroke parity**: ggplot2 `linewidth` is lwd units (measured ~2.13× heavier than points);
  the R templates convert preset point values so both backends draw equal stroke weights.
- `figure_id` hashes `PIPELINE_VERSION` + data sha256 + spec, so changing templates never leaves
  stale artifacts looking current.
- Pixi environment: Python 3.12 + matplotlib + numpy, and R ≥4.3 with ggplot2, svglite, ragg,
  systemfonts.

### Added — design judge and curation tools

- **Vision judge wired and measured**: OpenAI-compatible vision scoring of the design rubric, with
  image downscaling (`max_side`, default 768), tolerant JSON parsing, rationale stored, and an
  explicit fallback when no endpoint/key is available. Local `qwen2.5vl:7b` (Ollama) measured at
  ~145 s/figure on this CPU (1024 px: 367 s); `[design] max_side` trades detail for latency.
- **`gaxis design candidates <dir>`**: numbered contact sheet + `candidates.csv` of objective
  diagnostics for external curated figures (used to build a golden set from the WeChat palette
  series; 19 images downloaded, duplicates and non-figure assets flagged by inspection).
- **`gaxis design judge <image>`**: score one figure with the configured judge.
- `docs/vision-judge.md`: candidate models (Qwen-VL-Max, GLM-4.5V, GPT-4o-mini, Gemini Flash,
  Claude, local Qwen2.5-VL), rough costs, measured latency, calibration protocol.
- Local endpoints (Ollama) no longer require an API key; remote endpoints still fail loudly.

### Changed — correcting the quality model

- **Split "usable" from "good"**: `chart_quality_score` is now explicitly the *extraction gate*
  (caption, artwork, resolution, area, vector, crop cleanliness). Aesthetic and information-design
  quality is a separate object (`design`) judged by a rubric, not by pixel parameters.
- **Removed the aesthetic claim from the heuristic**: pixel-derived "aesthetics" rewarded technical
  parameters and mis-ranked real figures. The offline judge now only reports objective signals
  (legibility from PDF font sizes, caption-declared units/uncertainty/panels, colour-blind safety,
  chart-vs-photo, whitespace) and leaves `aesthetic`/`score` **null** until judged.
- **Vision judge** (`[design] judge = "vision"`): OpenAI-compatible vision scoring of the same
  rubric, rationale stored in the manifest, explicit fallback to the objective judge when no key or
  endpoint is configured.
- **Nature-family captions parsed**: `Fig. 1 | Title` (vertical bar) is a caption, `Fig. 4b,
  Supplementary Data` is a citation. One Nature Communications paper now yields 7/7 figures where
  the parser previously found one.
- **Corpus warning documented**: the previous calibration used low-quality figures and is marked
  invalid; design calibration requires a golden set of figures the owner considers excellent.
- Palette extraction fixed (near-white mask, anti-aliasing merge, chromatic-only counting),
  colour-blind check moved to chroma distance in Lab under Machado 2009 simulation.

### Added — extraction quality and calibration

- **`crop_clean` component**: pixel-level crop check (blank, body-text bands, clipped frame, tinted
  scan) so the quality score can disagree on a homogeneous corpus. Stored in
  `geometry.crop_clean`, computed at extraction, backfillable with `gaxis quality backfill`
  (which also re-ingests the KB). Weight added to `[quality]`.
- **Ranking protection**: `gaxis quality sheet` refuses to overwrite a sheet that already has human
  ranks (`sheet_has_ranks`, `--force` to override), and writes `rankings.template.csv`.
  `gaxis quality calibrate` accepts either the CSV or a filled-in `sheet.md`.
- `.gitignore` audited and rewritten: anchored `/data/`, `/dev/`, `/vendor/`, ignored `.env*`,
  downloads and editor/OS noise; fixed `data/` accidentally matching `tests/data/` (would have
  shipped a repo whose tests could not run).

### Added — semantic retrieval and R reproduction

- **Semantic retrieval enabled and measured**: ollama installed user-level, `bge-m3` (1024-dim)
  enabled in gbrain, `missing_embeddings` 0. Warm embed ~1.43 s/chunk, llama-server RSS ~1.4 GB.
  A Chinese query with no keyword overlap went from 0 hits to 3 (rarefaction figures).
- **R reproduction**: `gaxis-repro-r:4.5` (rocker/tidyverse + svglite/patchwork/cowplot);
  `.R`/`.Rmd` scripts run with `Rscript` in that image, the report records the image, and
  `reproduce_chart_code` returns `language`. Verified: ggplot bar chart reproduced with L2 (0.56).
- **Quality calibration tooling**: six explainable components (`caption`, `artwork`, `resolution`,
  `area`, `vector`, `cited`), configurable `[quality]` weights, `gaxis quality sheet` (Markdown +
  contact sheet) and `gaxis quality calibrate rankings.csv` (Spearman with ties, coordinate descent,
  TOML snippet). Sheet generated for the current corpus; calibration awaits human ranking.
- Fixed: R scripts were handed to the python image (sandbox image selection), and local R runs were
  executed with the python interpreter.

### Added (M1 completion: identifiers, downloads, paper code)

- **Identifier resolution**: DOI via Crossref + Unpaywall (open-access PDF), arXiv Atom API,
  PubMed E-utilities, PMC OA service, plain PDF URLs; parsers are pure functions with offline tests.
- **Bounded PDF download**: User-Agent, contact email, size cap, `%PDF` magic check, atomic write,
  cache by identifier.
- **Repository discovery**: GitHub/GitLab/Bitbucket/Zenodo links in the paper text (issue/blob URLs
  filtered), shallow clone with a size cap, plotting scripts scored by name + plotting evidence
  (`savefig`/`ggsave`/`ggplot`/`matplotlib`), attached to manifests as `code_candidates` with
  licence, language and dependency hints. Never executed during ingest.
- **Paywalls are reported, not circumvented**: metadata + `pdf_url: null` + a message telling the
  user to pass the PDF path.
- `with_code` request flag (default from `[ingest] with_code`) and result fields `pdf_url`,
  `repository_urls`, `code_candidate_count`; contract v1.5.

### Added (bacmap wiring)

- The upstream adapter now lives in bacmap at `src/bacmap/interfaces/mcp/upstream/gaxis.py` with
  `build_upstream(profile)`; `build_server()` registers it via `_register_gaxis_upstream`, gated by
  `BACMAP_GAXIS_URL` / `BACMAP_GAXIS_TOKEN` and fail-open (a broken gaxis never blocks bacmap).
- bacmap's pixi environment takes gaxis as an editable path dependency.
- Verified: 6 `bacmap_chart_*` tools under the cloud (D1) profile, 9 under local-trusted (D4);
  bacmap's own MCP interface tests still pass (64) plus 4 new adapter tests.

### Added (M3: knowledge-base ingestion and retrieval)

- **`search_chart_assets` is live** against gbrain `paper-kb` (federated source, page type
  `analysis`): caption + citing paragraph + visual grammar text, frontmatter filters pushed into
  gbrain (`--where`), level/preset filtering and ranking applied locally by
  (reproduction level, text score).
- **Page projection** (`kb/pages.py`): manifest → markdown with filterable frontmatter and bilingual
  chart synonyms, so a Chinese brief can hit an English paper.
- **Idempotent ingestion** (`gaxis kb ingest`): content-hash state in `data/kb/state.json`, skips
  unchanged pages, rewrites re-validated ones; runs automatically after `ingest_paper(mode="full")`.
- **Graceful degradation**: disabled/unreachable brain → `degraded: true` with the reason; a strict
  chart-type filter that hides a textual match is retried without the filter and says so.
- **`plan_chart_from_brief` attaches real cases**: matches, `candidate_asset_ids`, confidence bump.
- Verified on a real 43-page paper: 6 figure pages + 1 demo ingested (7 pages), text search returns
  the right figure, and `gaxis plan "phylogenetic tree"` attaches `pdf-958cda27/fig-2`.
- Test isolation hardened: an autouse fixture disables the KB so tests can never write into a real
  brain (this was caught after test runs polluted `paper-kb`; 22 synthetic pages were removed).

### Added (M2: sandboxed reproduction with grading)

- **`reproduce_chart_code` is live**: static scan → rootless-podman run → raster comparison →
  L1/L2/L3 → manifest update, with a `reproduction.json` evidence file per run.
- **Reproduction image** `gaxis-repro:py312` built from pinned `python:3.12-slim` +
  `matplotlib==3.11.2 numpy==2.5.5`; the resolved image id is recorded in every sandbox report.
- **Isolation verified from inside the container**: network blocked (`--network none`), read-only
  root, `--cap-drop ALL`, `no-new-privileges`, tmpfs `/tmp`, memory/CPU/pids caps, rw work dir and
  read-only `/data` mount. Timeouts remove the container.
- **Static scan**: `os.system`/`subprocess`/`eval`/`exec`/`ctypes`/credential paths block a run
  (recorded as `level: none, run_status: skipped`); network/absolute-write/pickle are warnings;
  GPL/AGPL refuses reuse.
- **Explainable grading**: similarity = 0.50 correlation + 0.25 (1−MAD) + 0.15 edge agreement +
  0.10 ink agreement, times an aspect-ratio penalty; L1 ≥ 0.85, L2 ≥ 0.55, failed runs L3 with a
  stderr tail. Every level stores its reason and components.
- **Two engines behind one port**: podman (production) and local (development, explicitly marked as
  unisolated); `gaxis reproduce … --engine` overrides per call.
- CLI `gaxis reproduce`, MCP tool wired to the kernel, contract v1.4.

### Added (M1 vertical slice: paper PDF → ChartReproManifest)

- **`ingest_paper` works for local PDFs**: page count, figures, captions (full text), citing
  paragraphs, DOI when present, quality score; `mode="kb_first"` parses without writing anything,
  `mode="full"` persists `assets/pdf-<sha8>/…` and `manifests/pdf-<sha8>__fig-<n>.json`.
- **Line-level caption detection** with delimiter/capitalisation/CJK rules, wrapped-caption merging,
  and margin line-number skipping — the three things that made real papers return zero figures.
- **Artwork extraction** from image XObjects, from vector bands verified by visible ink (watermarks
  excluded), and **cross-page pairing** for pre-proof layouts where artwork lives in a separate
  section. Caption-only figures are recorded honestly when the PDF contains no artwork.
- **`get_chart_manifest` is live**: reads the persisted manifest by id (relative paths, geometry,
  quality, notes), which closes service flow 2's inspection step for PDFs.
- `gaxis ingest` / `gaxis manifest` CLI commands; `pdf_unreadable` typed error for corrupt files.
- Verified on a real 43-page Journal Pre-proof paper: 6/6 figures, captions 193–774 characters,
  citing paragraphs matched, quality 0.85.

### Added — KB-first flow, configuration, panels (contract v1.3)

- **`ingest_paper` now classifies and routes for real**: PDF / DOI / arXiv / PubMed / PMC / URL,
  with `normalised_id` for dedupe, network permission enforced (`network_disabled`), and
  `mode="kb_first"` as the default — show knowledge-base matches before paying for deep parsing.
  Parsing/reproduction remain M1/M2.
- **Configurable confirmation**: `gaxis.toml` `[confirmation] mode = auto|always|never` and
  `min_confidence`; `plan_chart_from_brief` returns `requires_confirmation`,
  `confirmation_threshold`, `confirmation_mode` so hosts stop inventing thresholds.
- **Typed configuration file** (`gaxis.example.toml`): `[confirmation]`, `[render]`, `[ingest]`,
  `[knowledge]`, with a documented env-override list and loud `config_invalid` failures.
  `gaxis config` shows the effective values; `--config` selects a file.
- **Panel composition hooks**: `GAXIS_PANEL_SOURCE=1` makes an emitted `figure.py`/`figure.R` build
  the figure without saving, so later patchwork/cowplot composition keeps vector output; panel
  manifests keep the evidence chain. `compose_panels` itself is M4.
- Snapshot renamed to `tests/contract_snapshot.json` and now carries the contract version, so
  future bumps no longer rename files.

### Added — service flows (contract v1.2)

- **`plan_chart_from_brief`** (service flow 1, step 1): turns a natural-language figure request into
  a data-free `ChartPlan` — chart type, journal preset, palette, backend, required column roles,
  style notes, open questions and a confidence score. Deterministic, bilingual (EN/中文), no LLM
  call. CLI: `gaxis plan "grouped bar with error bars, mBio"`. KB matches arrive at M3.
- **`ingest_paper`** (service flow 2, entry): typed contract for on-demand paper ingestion
  (DOI/arXiv/URL/PDF) returning manifest ids; parsing and reproduction were completed in M1/M2.
- Contract grows to **v1.2 / nine tools**; snapshot refreshed (`tests/contract_snapshot.json`), MCP
  server, typed client and bacmap adapter pick the new tools up automatically.
- `docs/service-flows.md`: both flows step by step, what is ready vs planned, the convergence rules
  a host LLM must follow, and the questions the knowledge base must be able to answer.

### Added (knowledge base groundwork)

- **gbrain installed and verified in the pixi environment**: `pixi run gbrain-install` vendors upstream
  0.60.740.0 plus a pinned bun 1.4.4 (conda-forge ships 1.4.2, which gbrain rejects) and drops a shim
  into the env; `pixi run gbrain-init` creates the brain under `$XDG_DATA_HOME/gaxis/gbrain`.
- Isolated source `paper-kb` with `--no-federated` (only searched when explicitly named), verified
  write/read/delete paths, frontmatter filtering (`--where chart_type=…`), and page-type constraint
  (`analysis` accepted, undeclared types rejected).
- `examples/paper-kb-page.example.md`: the page shape gaxis will derive from a `ChartReproManifest`.
- `docs/gbrain-integration.md` rewritten from measurement: install layout, isolation rules, write
  semantics (`revision_required` / `--force` / `content-origin`), read filters, and the
  text-only-vs-multimodal decision with two concrete upgrade paths.

### Changed

- Legends moved outside the axes in the matplotlib backend (a journal figure must not cover data
  with its own key) — this also aligns the Python layout with the ggplot2 backend.
- Heatmaps: the y axis is now labelled with the grouping factor and the colour bar with the
  measured variable; annotations pick black/white text by cell luminance in both backends.
- `scripts/review_matrix.py` (`pixi run review`): renders a 6 chart x 3 preset x 2 backend matrix,
  writes `data/review/REVIEW.md` and `contact-sheet.png` as the standalone acceptance artifact.
  Current state: 36/36 renders lint-clean.

### Known limits in 0.1.0

- Scanned PDFs without a text layer are not OCR'd; they yield no figures and say so.
- Only delimited tables (CSV/TSV) are supported; Excel/Parquet/JSON are not.
- Paper repositories are cloned and their plotting scripts detected, but their bundled data is not
  discovered automatically; `reproduce-paper --synthetic` is the labelled fallback.
- Image retrieval is perceptual (dHash), not semantic; there is no CLIP-style visual index.
- Composition is a rectangular grid; nested layouts and shared axes are not implemented.
- `dev/plan.md` and `dev/decisions.md` are owner-local and not committed; this changelog and
  `DESIGN.md` are the committed record.
## Upcoming

- Wire `integrations/bacmap_upstream_gaxis.py` into the bacmap repository (adapter tested here).
- Repository-bundled data discovery, table/SI parsing, OCR for scanned PDFs.
- Semantic image retrieval, graph traversal across assets, nested composition layouts.
- Pi / DSH / Hermes adapters and deployment artefacts (container image, service unit).
