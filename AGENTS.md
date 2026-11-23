# AGENTS.md

Guidance for coding agents (and humans in a hurry) working in this repository.

## What this project is

**gaxis** turns a tidy data table into a **publication-grade figure plus the standalone script that
produced it**, and (from M1 on) turns paper figures into verified, reusable figure code.

One sentence to keep in mind while coding:

> The figure, the script, and the manifest are one artifact. If any of the three can drift from the
> others, the design is wrong.

Two surfaces, one kernel:

1. **MCP server** (Streamable HTTP) consumed by bacmap, DSH, Pi, Hermes and anything else that
   speaks MCP. bacmap is the primary research consumer.
2. **CLI** for a researcher at a terminal, offline, no knowledge base required.

## Ground truth documents

| File | Status | Contents |
|---|---|---|
| `dev/plan.md` | local only, **not committed** | product plan v2.0 (user-owned) |
| `dev/decisions.md` | local only, **not committed** | decisions and open questions log |
| `DESIGN.md` | committed | architecture, contracts, module map |
| `docs/mcp-tools.md` | committed | per-tool reference (v2.6 contract) |
| `docs/presets.md` | committed | journal presets and lint rules |
| `docs/bacmap-integration.md` | committed | host wiring, data-class gating, failure modes |
| `docs/service-flows.md` | committed | the two product flows, tool-by-tool, ready vs planned |
| `docs/gbrain-integration.md` | committed | verified gbrain surface: install, isolation, write/read paths, multimodal stance |

When `dev/plan.md` and `DESIGN.md` disagree, ask — do not silently pick one.

## Hard rules

These are non-negotiable; a change that violates one needs an explicit decision in
`dev/decisions.md` first.

1. **Tool contract is frozen.** Twelve tools (v2.6): `health`, `describe_data_schema`,
   `render_chart_from_data`, `plan_chart_from_brief`, `search_chart_assets`,
   `get_chart_manifest`, `ingest_paper`, `reproduce_chart_code`, `adapt_chart_code`,
   `compose_panels`, `list_figure_recipes`, `render_figure_recipe`. Changing names,
   inputs or outputs requires bumping the contract version, refreshing
   `tests/contract_snapshot.json` via `pixi run python scripts/freeze_contract.py`, and updating
   `docs/mcp-tools.md` + `docs/service-flows.md`.
2. **Core never imports a host SDK.** No `import bacmap`, no DSH/Pi/Hermes SDKs under
   `src/gaxis/{models,spec,style,render,exec,service.py}`.
3. **Host adapters are thin.** Anything that binds a host SDK — `integrations/*`, and later
   `src/gaxis/adapters/{pi,dsh,hermes}.py` — stays ≤ 150 lines, holds no business logic, and never
   imports another adapter. `adapters/cli.py` is first-party UX and may be longer, but every command
   must be a thin call into `service.py`.
4. **Generated code never imports gaxis.** The emitted `figure.py` / `figure.R` must run in a plain
   Python/R environment. This is what makes it a deliverable instead of an artifact.
5. **Every render writes `manifest.json`** with `data.sha256`, `code_sha256`, outputs and the lint
   report. Evidence binding is a product requirement (ADR-08), not a nice-to-have.
6. **Dual backend parity.** Any chart capability ships in **both** matplotlib and ggplot2, or it
   does not ship. The user explicitly requires R at M0.
7. **No silent degradation.** A missing font, a missing preset, a fallback backend, a skipped
   sandbox — all must appear in the lint report or the manifest. Never swallow.
8. **`health` is read-only.** It must not render, download, acquire a lock, or write anything.
9. **Data classification at the boundary.** Every tool declares `data_class` (`D1`–`D4`) so a host
   like bacmap can gate by profile before execution. Adding a tool without it is a bug.
10. **Python 3.12 only.** Deps come from conda-forge via pixi; new deps need a reason in the PR/commit
    message.
11. **Sandbox = rootless podman** by default (`[sandbox] backend`). The `local` engine exists for
    development and tests; its report must always say `network_enforced: false, read_only_root:
    false`, and it is never evidence of safe execution. Both engines implement `sandbox/base.py`.
12. **gbrain state lives outside the repository.** `GBRAIN_HOME` defaults to
    `${XDG_DATA_HOME:-~/.local/share}/gaxis/gbrain`; a source path inside this worktree is refused by
    gbrain and risks committing a database. Nothing may write to `~/.gbrain`.
13. **Bump `service.PIPELINE_VERSION` when templates or emission change.** `figure_id` hashes the
    pipeline version, the data and the spec, so stale code can never be mistaken for current output.
14. **Configuration is a TOML file, not flags scattered through code.** `gaxis.example.toml` is the
    template; `[confirmation]`, `[render]`, `[ingest]`, `[knowledge]` are the supported tables.
    Env overrides are limited to `GAXIS_*` names listed in `config.ENV_OVERRIDES`. A broken config
    must raise `config_invalid`, never fall back silently.
15. **Knowledge base = gbrain, `paper-kb` source, `federated=false`** (verified: such a source is only
    searched when explicitly named). Never mix paper-figure semantics into other sources. Pages are a
    derived index — rebuildable, never the source of truth; manifests are.

## Documentation

The site under `docs/` is bilingual: `page.md` is English (default), `page.zh.md` is Simplified
Chinese (`mkdocs-static-i18n`, suffix mode). Every page must exist in both languages, links inside
`.zh.md` point at `.zh.md`, and new titles go into `nav` + the `zh` `nav_translations` map. Build
with `pixi run docs-build` (strict).

## Commands

```bash
pixi install                       # python 3.12, matplotlib, R + ggplot2
pixi run check                      # ruff + ruff format --check + mypy + pytest (must be green)
pixi run test
pixi run fmt

pixi run gaxis health
pixi run gaxis presets
pixi run gaxis palettes
pixi run gaxis tools                # machine-readable tool contract
pixi run gaxis plan "grouped bar with error bars, mBio"   # service flow 1, step 1
pixi run gaxis config                 # effective config (file + env)
pixi run gaxis ingest paper.pdf --mode full     # service flow 2: figures -> manifests
pixi run gaxis manifest pdf-<sha8>/fig-1 --json
pixi run gaxis reproduce pdf-<sha8>/fig-1 --code figure.py [--engine podman|local]
pixi run gaxis ingest 10.1099/mgen.0.000001 --mode full   # resolve + download + repo + KB
pixi run gaxis kb status
pixi run gaxis kb ingest [--force]
pixi run gaxis kb search "rarefaction curve" --min-level L2
pixi run gaxis kb search --schema data.tsv --tier gold --sheet   # data-shaped selection
pixi run gaxis reproduce-paper pdf-<sha8> [--data table.csv] [--synthetic] [--reconstruct-missing]
pixi run gaxis reconstruct pdf-<sha8>/fig-1 [--data table.csv] [--repair]
pixi run gaxis kb seed                     # verified builtin templates -> KB (idempotent)
pixi run gaxis kb adopt pdf-<sha8>/fig-1   # reproduced paper script -> adaptable template
pixi run gaxis analysis run amr-cooccurrence --input amr.csv --out data/analysis
pixi run gaxis render --chart network --data edges.csv --x source --y target --weight weight
pixi run gaxis analysis scaffold snp-tree --out workflows/snp-tree --alignment aln.fasta --check
pixi run gaxis analysis run newick-to-table --input tree.nwk --out data/analysis
pixi run gaxis render --chart tree --data tree_edges.csv --x parent --y child --weight branch_length
pixi run gaxis adapt --data data.tsv --preset asm --query "bar chart"
pixi run gaxis quality sheet            # human-ranking sheet for score calibration
pixi run gaxis quality backfill        # recompute crop_clean + scores, then re-ingest
pixi run gaxis quality calibrate data/calibration/sheet.md
pixi run gaxis compose --panels <id>,<id> --layout 1x2 --preset nature_microbiology
pixi run gaxis ops enqueue <doi> && pixi run gaxis ops run --limit 5
pixi run gaxis ops enqueue --kind reproduce pdf-<sha8> && pixi run gaxis ops run
pixi run gaxis ops verify                  # requeue done jobs whose evidence vanished

# MCP server (Streamable HTTP, bearer token required)
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
pixi run gaxis-mcp --transport http --port 8770
pixi run gaxis describe --data examples/demo/expr.tsv
pixi run gaxis render --data examples/demo/expr.tsv --preset nature_microbiology --out data/demo
pixi run gaxis render ... --backend r
pixi run gaxis lint data/demo/<figure-id>/<figure-id>.pdf --preset nature_microbiology
pixi run review                     # 36-figure matrix + contact-sheet.png + REVIEW.md (human review)
pixi run docs-serve                 # user docs (MkDocs Material) at http://127.0.0.1:8000/gaxis/
pixi run docs-build                 # strict site build; broken links/nav fail

pixi run gbrain-install             # vendor gbrain + pinned bun, shim into the pixi env
pixi run gbrain-init                # brain under $XDG_DATA_HOME/gaxis/gbrain
pixi run gbrain doctor
pixi run gbrain search "rarefaction" --source-id paper-kb --json
pixi run python scripts/freeze_contract.py
pixi run pytest -q tests/test_mcp.py tests/test_bacmap_upstream.py   # transport + host adapter
```

## Layout

```
src/gaxis/
  adapt.py    KB template -> local data: verified constant rebinding
  (kb/adopt.py) reproduced paper script -> template (DATA_PATH contract)
  compose.py  multi-panel page composition (vector, PyMuPDF)
  analysis/    table -> table recipes (AMR co-occurrence; no bioinformatics re-calling)
  ops/        checkpointed queue (SQLite): ingest + reproduce jobs
  repro/batch.py  reproduce a paper's suitable figures (explicit needs_data/needs_env)
  repro/synthetic.py  labelled synthetic input when the paper's data is absent
  models/     pydantic contract: ChartSpec, DataSchema, FigureManifest, tool I/O, lint
  spec/       inference: schema -> ChartSpec; brief.py: natural language -> ChartPlan
  style/      presets (TOML), palettes, rcParams, lint (file-level, backend-agnostic)
  render/     emit.py + templates/ (python_*.tpl, r_*.tpl) -> standalone script
  exec/       runner.py: run a script locally, capture logs/timeout
  adapt.py    KB template -> local data (verified constant rebinding)
  compose.py  multi-panel vector composition (PyMuPDF)
  service.py  the ten tool implementations, transport-neutral
  client.py   typed thin client for hosts (async, one connection, ten calls)
  mcp/        MCPServer (mcp 2.x) + Streamable HTTP with mandatory bearer auth
  adapters/   cli.py now; pi/dsh/hermes later (thin)
  acquire/   identifiers.py (source kind), paper.py (persist manifests)
  parse/     pdf.py (PyMuPDF), captions.py (label/citation heuristics)
  repro/     runner.py (orchestration), batch.py, synthetic.py, compare.py, grade.py
  sandbox/   base.py (port), podman.py, local.py, scan.py, image.py
  kb/         gbrain pages, ingestion, templates, adoption, feedback
integrations/ reference host adapters (bacmap client, results exporter), tested against a live server
examples/     demo inputs (examples/demo) + a reference gbrain page derived from a manifest
vendor/       untracked: gbrain checkout + pinned bun (pixi run gbrain-install)
scripts/      review_matrix, freeze_contract, corpus curation, gbrain wrappers
tests/        unit + e2e (python and R) + contract snapshot + MCP transport
dev/          untracked (owner-local): plan and decisions only
```

## Conventions

- All cross-module data is a pydantic model in `models/`; no bare dicts across boundaries.
- Failures raise `GaxisError(code, message, hint)`. Codes are stable strings (`render_failed`,
  `unknown_column`, `not_numeric`, `data_not_found`, `bad_parameter`) — hosts branch on them.
- Lint issues have numeric codes (`L001`…`L009`). Never reuse a code for a different check.
- Presets and palettes are data (`style/journal_presets/*.toml`, `style/palettes.py`), not code
  branches in templates.
- Templates live in `render/templates/*.tpl` with `@PLACEHOLDER@` markers; keep generated code
  readable — it is read and edited by humans and reviewers.
- Type annotations everywhere; `mypy src` must stay clean (`ignore_missing_imports` is on, so
  annotate your own code properly).
- Line length 100, ruff selects `E,F,I,UP,B,SIM,RUF,C4,PT`.

## Network and repository rules (M1)

- Network use is opt-in (`[ingest] allow_network`, default true here) and always bounded: a
  User-Agent with the project name, a contact email for Unpaywall/NCBI (`[ingest] contact_email`),
  PDF size cap, repository size cap and timeouts.
- **Cloned code is data, never something we run during ingest.** Only `reproduce_chart_code` executes
  it, and only in the sandbox after a static scan.
- A paywalled paper is a normal outcome: return metadata, `pdf_url: null` and the reason. Do not
  scrape, do not guess a PDF URL.
- Attach a script to a manifest only with a recorded `pairing_confidence` and licence; a GPL repo is
  still recorded (for logic reuse) but never copied into a template.

## Sandbox rules (M2)

- **Paper code runs in podman by default** (`[sandbox] backend`). The `local` engine exists for
  development and tests; its report must always say `network_enforced: false, read_only_root: false`.
  Never present a local run as evidence of safe execution.
- **Never weaken a guard silently**: network, read-only root, cap-drop, pids/memory/CPU limits and
  `no-new-privileges` are defaults. Changing one requires an explicit config key and a test.
- **A blocked run is an outcome, not an error**: return `level: "none"`, `run_status: "skipped"` and
  the reason. Same for copyleft licences.
- **Image ids are evidence**: any run records the resolved image id (`sandbox_report.image_id`).
  Rebuilding the image invalidates old grades — say so rather than comparing across image versions.
- **Grading thresholds live in `[reproduction]`**, never hardcoded in the runner or the tests.
- R/ggplot2 reproduction uses `[sandbox] r_image`; without it, `.R` scripts are refused rather than
  run locally by accident.

## Design quality (read `docs/design-quality.md`)

- **Never call the extraction score "quality".** It is a usability gate. Aesthetic/visualization
  quality is `design`, judged against the rubric; if it has not been judged, it stays `null`.
- **Do not invent aesthetics from pixels.** Heuristic palette/whitespace signals are diagnostics,
  not a taste model; they may screen, they may not rank as "good design".
- Vision judge output must be calibrated against a human ranking of a golden set (ρ ≥ 0.7) before
  its scores drive selection. Store the model name and rationale; a silent model swap invalidates
  comparisons.
- The judge speaks OpenAI-compatible chat completions; local Ollama endpoints need no key but are
  slow (~145 s/figure at 768 px here). `[design] max_side` is the latency knob, not a quality cheat.
- `gaxis design candidates <dir>` builds the golden-set sheet; keep objective columns labelled as
  diagnostics, never as a substitute for the human ranking.
- **Tiers are policy, not truth**: `gold ≥ 0.55`, `dense 0.45–0.55`, `reject < 0.45` live in
  `[design]`. `reject` figures remain extraction assets but are not indexed; a re-judged figure that
  falls below the threshold has its page removed (`IngestSummary.removed`). Never widen this
  silently or index them without an explicit config change and a test.
- The golden set (22 curated + 8 counterexamples) is the regression baseline. If you change the
  rubric/model, re-judge, refresh `tests/data/golden_design_judgements.json` deliberately, and
  explain why in the commit.

## Quality and embeddings (M3+/M4 prep)

- **Quality weights live in `[quality]`**, never inline in the extractor. Changing them invalidates
  existing scores: re-run `kb ingest` so pages and ranking follow.
- **Calibration needs a human**; the tooling only fits weights. Do not fabricate a ranking file and
  call it calibration. A sheet with ranks is never overwritten (`--force` is deliberate).
- **Embeddings are optional infrastructure**: bge-m3 via ollama (~1.4 GB RSS, ~1.4 s/chunk here).
  gbrain must keep working with keyword search when ollama is down (`degraded: embed_unavailable`),
  and tests must not require ollama.

## Paper parsing rules (M1)

- **Never fabricate artwork.** If a PDF has a caption but no figure (pre-proof, separate figure
  files), record a caption-only manifest with an explicit note. A cropped body paragraph in the KB is
  worse than a missing image.
- Extracted geometry is evidence: keep `geometry.page/bbox/source` and the pairing note, so a wrong
  pairing can be diagnosed instead of silently trusted.
- Heuristics live in `parse/captions.py` (pure, testable) and `parse/pdf.py` (PyMuPDF). Add a fixture
  case for every layout quirk you fix (single column, two column, captions-before-artwork, no artwork).
- `ChartReproManifest` paths are relative to the data root; nothing may store an absolute path.

## Knowledge base rules (M3)

- **Pages are derived; manifests are authoritative.** Never let a page become the only copy of a
  fact, and never hand-edit a page in a way that cannot be regenerated.
- **Ingest is idempotent and hash-based.** If you change page rendering (`kb/pages.py`), changed
  pages are rewritten automatically; no manual cache busting.
- **Retrieval must not hide results silently.** A filter that removes everything gets a retry
  without the filter plus an explicit message. `degraded` means "brain unavailable", never "empty".
- **Tests must never touch a real brain.** The autouse fixture sets `GAXIS_KB_ENABLED=false`; a test
  that needs the KB uses `fake_kb` (tests/fake_gbrain.py). If you write a test that shells out to
  `gbrain`, you are doing it wrong.
- **Reproduction level drives ranking.** Fresh manifests with `level=none` rank last on purpose; do
  not "fix" that by defaulting to L3.

## Known SDK quirks (mcp 2.x)

- `ClientSession(read_timeout_seconds=...)` is added to a monotonic float internally: pass
  **seconds as a float**, not a `timedelta`, or you get `float + timedelta`.
- Registering a tool whose signature has a second parameter (even with a default) leaks that
  parameter into the JSON Schema. Build handlers through a closure instead.
- A failed handshake can leave anyio task groups pending; `GaxisClient.__aenter__` closes its stack
  on failure, and the bacmap adapter preflights the socket so "server down" never enters the SDK.
- Structured tool results arrive as `structured_content`; fall back to `content[0].text` (see
  `client._payload`).

## Definition of done

1. `pixi run check` green.
2. New behaviour has a test (e2e for rendering, unit for inference/lint).
3. Python **and** R backends produce a lint-clean figure for any new chart type.
4. Manifest still carries both sha256 fields and the lint report.
5. Docs touched: `DESIGN.md` for architecture, `docs/mcp-tools.md` for contract, `CHANGELOG.md`
   for user-visible changes.
6. If a decision was made, it is written down in `dev/decisions.md`.

## Things that are deliberately not here

- No genome/species data acquisition, no analysis pipelines, no metadata DB import (plan §1.2).
- No LLM calls inside the render path. Figure generation is deterministic; retrieval and paper
  parsing may use models, but a render must be reproducible byte-for-byte given the manifest.
  LLM figure reconstruction is a separate, explicitly labelled path (`reproduction.method`);
  it never claims to be author-code reproduction.
- No `stdio` MCP transport in production (ADR-02); it may exist for local debugging only.
