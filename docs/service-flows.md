# Two Service Flows (Product Core)

This project does exactly one thing: **turn high-quality figures from papers into code assets that are "verified, searchable, and adaptable", then use them to help users draw their own paper figures.**

This takes the form of two service flows. They are the backbone of the product; periodically scraping papers, parsing figures and code, and sandbox reproduction all exist to stockpile ammunition for these two flows.

```
┌───────────────────────── Background: periodic scraping (modules A/B/C/D/H, M1–M2) ─────────────────────────┐
│ paper sources → quality filter → figure/caption/citation/code → sandbox reproduction → L1/L2/L3 → paper-kb │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                    │ knowledge base stockpile (gbrain paper-kb, federated=false)
                                    ▼
   Service 1: chart from natural language          Service 2: give me a paper, draw a similar figure
   brief → cases → converge → plan/data/code       paper → recognize → suggest → adapt to my data
```

---

## Service 1: Natural language → cases → conversational convergence → plan/data/code

### 1.1 Flow

| Step | Who | Call | Output |
|---|---|---|---|
| 1 | Host LLM | `plan_chart_from_brief(brief)` | **ChartPlan**: chart type, journal preset, style points, required column roles, questions to confirm, candidate cases |
| 2 | Host LLM | (in conversation) resolve each `open_questions` item one by one, revising the brief / spec according to the user's answers | a converged draft ChartSpec |
| 3 | Host LLM | `search_chart_assets(query, filters)` | **Available (M3)**: cases from the knowledge base (asset_id, reproduction level, thumbnail path, DOI) |
| 4 | User | provide data (CSV/TSV) | — |
| 5 | Host LLM | `describe_data_schema(data_path)` | column profiles, suggested spec, unit hints |
| 6 | Host LLM | `adapt_chart_code(data_path, asset_id/query)` or `render_chart_from_data(...)` | figure + standalone script + manifest + lint |
| 7 | User | review the contact sheet / script, request changes | back to 2 or 6 |

Key point: **step 1 needs no data**. Users often first discuss "what chart do I want", with the data arriving later. That is the sole reason `plan_chart_from_brief` exists in the contract.

### 1.2 What can be done now (implemented)

```bash
$ pixi run gaxis plan "grouped bar chart with error bars, Nature Microbiology, ggplot2, colour-blind palette"
chart:    bar   preset: nature_microbiology   backend: r   confidence: 0.85
style:
  - error bars: mean ± SD across replicates by default; pass a `yerr` column to supply SEM or 95% CI instead
columns:
  - x     categorical 2-12 groups
  - y     numeric     measurement per observation (omit to count rows)
  - hue   categorical grouping factor, 2-8 levels (colour/fill)
ask the user:
  ? Error bars: SD, SEM, or 95% CI? (and how many replicates per group)
  ? Attach the table (CSV/TSV, one observation per row) or describe its columns
note: knowledge base disabled ([knowledge] enabled = false) …
```

- Briefs in both Chinese and English (a brief like "draw a grouped bar chart with error bars, colour-blind friendly, for mBio" is recognized just the same);
- Chart type / journal preset / palette / backend / error bars / multi-panel / log axes / legend position are all recognized; **anything unrecognized goes into `open_questions`, never silently guessed**;
- `confidence` and `degraded` state explicitly that "this is a heuristic draft, not a retrieval result";
- Once data is available, `render_chart_from_data` / `adapt_chart_code` are real, working paths (6 chart types × 2 backends × 7 journal presets, 36/36 lint clean).

**M3 is complete**: when the knowledge base is available, `plan_chart_from_brief` puts retrieved cases into `matches`, writes their asset_id into `plan.candidate_asset_ids`, and raises `confidence` by hit count (+0.05 each, capped at 0.9). If nothing in the KB matches, `message` says plainly "no knowledge-base case matched" instead of pretending a search happened.

### 1.3 Conventions for conversational convergence (for the host LLM)

- Before rendering, the user must confirm three things: **chart type**, **statistical convention** (error bars: SD/SEM/CI, and how many replicates), **target journal/column width**.
- When `confidence < 0.6` or `degraded`, do not render directly; go through `open_questions` first.
- When the user has only given a screenshot or a description and no data: only provide `plan` + cases; fabricating data to render is forbidden (optional later: clearly labeled synthetic data, after M2).
- `lint.issues` in the render result must be presented to the user verbatim; reporting only "success" is not allowed.

---

## Service 2: The user gives a paper; draw figures like those in it

### 2.1 Flow (knowledge base first)

Explicit principle: **first check whether the knowledge base already has something that satisfies the need; only then decide whether to spend time parsing the paper and reproducing its code.**

| Step | Who | Call | Output |
|---|---|---|---|
| 1 | Host LLM | `ingest_paper(source, mode="kb_first")` | source identification (PDF / DOI / arXiv / PubMed·PMC / URL) + list of the paper's figures (`figure_briefs`) + in-KB matches (from M3 on, can be drawn from already-ingested assets) + whether deep parsing is worthwhile |
| 2 | Host LLM | present the matches to the user (thumbnail + reproduction level + style notes) | user judges: good enough / not good enough |
| 3a | Good enough → | `adapt_chart_code(data_path, asset_id, preset)` | figure + code + manifest (Service 2 complete) |
| 3b | Not good enough → | `ingest_paper(source, mode="full")` | deep parsing: `get_chart_manifest` → `reproduce_chart_code` → new L1/L2/L3 assets into the KB |
| 4 | Host LLM | `search_chart_assets(query=figure semantics, filters)` | similar cases (including implementations better than the original's) |
| 5 | Host LLM | `adapt_chart_code(...)` | adapt to the user's data → figure + code + manifest |
| 6 | User | proofread / revise | back to 5 |

`mode="kb_first"` is the **default** (`[ingest] default_mode` in the config file), because it is cheap: no repo download, no environment build, no sandbox run — it answers "is it in the KB?" within seconds. Only when the user is unsatisfied with what the KB offers do they pay the cost of `mode="full"` (minutes, requires network, runs code).

Source types (`source_kind`, determined offline, `src/gaxis/acquire/identifiers.py`):

| Type | Example | Needs network |
|---|---|---|
| `pdf` | `/path/paper.pdf` | No |
| `doi` | `10.1099/mgen.0.000001`, `https://doi.org/…` | Yes |
| `arxiv` | `arXiv:2103.00020`, `2103.00020v2` | Yes |
| `pmid` / `pmcid` | `PMID:12345678`, `PMC7654321` | Yes |
| `url` | publisher pages, preprint pages | Yes |

`normalised_id` is used for deduplication: `https://doi.org/…` and a bare DOI collapse into the same entry, and the `PMID:` prefix is stripped. When the network switch `[ingest] allow_network = false` is set, networked types report `network_disabled` outright (local PDFs are unaffected).

### 2.2 What can be done now

| Capability | Status |
|---|---|
| `ingest_paper` | **Available**: source identification, id deduplication, network policy, `kb_first/full` routing, PDF parsing, code repo cloning and script selection |
| `get_chart_manifest` | **Available**: full manifest (code candidates, reproduction level, scoring) |
| `reproduce_chart_code` | **Available**: podman/local sandbox, similarity decomposition, L1/L2/L3, code assetization, automatic KB refresh |
| `search_chart_assets` | **Available**: text / table-structure / image dHash retrieval, design tiers and code filtering, contact sheet |
| `adapt_chart_code` | **Available**: retrieve a verified template → rebind data path/columns/separator → trial run; degrades when something is missing and reports `fallback_reason` |
| Candidate figure selection | **Available**: `schema_path` (data only), `design_tier`/`has_code` filtering, deduplication, `render_sheet` |
| Batch reproduction | **Available**: `reproduce-paper` / `ops enqueue --kind reproduce`, selected by pairing confidence, explicitly returning `needs_data`/`needs_env` |
| User-data adaptation + lint + manifest | **Available** |

Parts not yet wired up: auto-installing paper-repo dependencies already has per-paper mirrors (`requirements.txt`/`DESCRIPTION`), but in-repo data discovery, table/supplementary (SI) parsing, and OCR for scanned PDFs remain to be implemented; the corresponding limitations are stated in the feature documentation, not hidden.

### 2.3 Where the judgment logic lives

The judgment of "can I draw the figures in this paper, and how would you suggest drawing them" is **not hard-coded into gaxis**:

- gaxis provides the facts: figure quality scores, reproduction levels, dependencies, input schema, license, sandbox run results, lint.
- The host LLM provides the judgment: whether reproduction is worthwhile, whether a clearer presentation should be used instead, whether the user's data is sufficient.
- This follows directly from ADR-01/05: the kernel does no free-form "paper understanding"; it only supplies auditable facts and runnable artifacts.

---

## Confirmation before rendering: thresholds live in the config

`ChartPlan` carries `requires_confirmation / confirmation_threshold / confirmation_mode`, decided by `gaxis.toml`; the host LLM does not need to invent its own rules:

```toml
[confirmation]
mode = "auto"          # auto | always | never
min_confidence = 0.6   # in auto mode, below this the host must confirm first
```

- `auto` (default): when confidence ≥ the threshold, render directly; below the threshold, confirmation via `open_questions` is required;
- `always`: always confirm (safer for submission scenarios);
- `never`: never ask (batch rendering / scripted use, at your own risk).

Environment variables can override temporarily: `GAXIS_CONFIRM_MODE`, `GAXIS_CONFIRM_MIN_CONFIDENCE`. Config precedence: `--config` > `$GAXIS_CONFIG` > `./gaxis.toml` > `~/.config/gaxis/config.toml` > defaults; `pixi run gaxis config` shows the effective values. A template is at `gaxis.example.toml`.

## Multi-panel: single panels first, composition later (decided)

The user first completes single-panel figures one by one (each one is an independent figure: its own `figure.py`/`figure.R`, manifest, lint), and does the panel assembly later. Two prerequisites are therefore built in now:

1. **Panel scripts can be "source-included" without hitting disk**: run `figure.R` / `figure.py` with `GAXIS_PANEL_SOURCE=1` set; the script only builds the plot object and writes no files — patchwork/cowplot (R) or subfigure (matplotlib) can consume it directly for layout, and vector output is not rasterized.
2. **The evidence chain is composable**: every panel has `figure_id` + manifest (`code_sha256`, `data.sha256`); the future `compose_panels` only needs to reference the child manifests instead of re-rendering.

`compose_panels` (contract v2.6) is already available: it places the **PDF** of already-rendered panels directly onto one page (vectors preserved, nothing re-drawn), arranged by `ROWSxCOLS` or an automatic grid, with optional A/B/C labels, and outputs a `CompositionManifest`:

```
CompositionManifest {
  composition_id, panels: [{manifest_id, label: "A"|"B"|…, code_sha256}],
  layout: (rows, cols), preset, width_mm/height_mm, output_pdf/output_png, lint
}
```

R route (preferred, user-specified): `patchwork`/`cowplot` source-includes the panel scripts → `wrap_plots`/`plot_grid` → a single `ggsave` writes PDF/SVG; fallback route: vector merging (`pdfjam`/`qpdf`) or `magick` (rasterizes; not for submission). Journal size/font-size rules for multi-panel figures need their own preset set (e.g. 183 mm double column, panel labels 8 pt bold), to be added later at M4 together with `[presets]`.

## Background flow: periodic scraping and reproduction (module H)

Not MCP tools, but scheduled jobs running outside the resident service:

1. Scrape papers ordered by quality score (A);
2. Parse figures, captions, citing paragraphs, repo code (B);
3. Build environments, synthesize input schemas, run in the sandbox, compare renders, assign L1/L2/L3 (C/D);
4. Write into `paper-kb` (a non-federated source, see `docs/gbrain-integration.md`);
5. Persist checkpoints so interrupted runs can resume; low-tier assets still enter the KB but are down-weighted in retrieval with the reason annotated (ADR-10).

Its output is the "ammunition" for Services 1/2. Acceptance metrics: see `dev/plan.md` §8.2/8.3 (L1+L2 run success ≥70%, L1 visual pass ≥60%, Top-5 hit rate ≥70%).

---

## What the two flows require of the knowledge base (designed accordingly)

Every asset page (gbrain `type: analysis`) must at least be able to answer:

| Field | Use for the services |
|---|---|
| `chart_type` + `visual_grammar` (text) | Service 1's "find a chart from a text description"; Service 2's "similar charts" |
| `reproduction_level` / `sandbox_run_status` | retrieval down-weighting, trustworthiness, Service 2's "can it be used as-is" |
| `dependency_hints` / `input_schema_hints` | Service 2's feasibility judgment for adaptation |
| `code_path` + `code_sha256` | deliverables and auditability |
| `image_path` (relative path, resolved via asset_id) | multimodal hosts view the image directly, not through gbrain |
| `license` | copyleft licenses: only rewrite the logic, never reuse directly |
| `paper_id` / `doi` / `caption` / `citing_paragraph` | citation and provenance |

The page format follows `examples/paper-kb-page.example.md`; retrieval is verified to support `--where chart_type=line --where reproduction_level=L1`.

---

## Confirmed (2026-11-18)

1. The entry point accepts **documents (PDF) and identifiers such as DOI / PubMed ID** — offline classification and deduplication are implemented; networked parsing comes in M1.
2. Service 2 is **knowledge-base-first**: parse the paper's figure needs first; if the KB has matching items, show them to the user first; only if the user is unsatisfied do we deeply parse the paper's implementation — `mode="kb_first"` is the default; only `full` pays the parse/reproduce cost.
3. **Confirmation thresholds live in the config file**: `auto/always/never` + `min_confidence`; the host does not have to decide on its own — implemented.
4. **Multi-panel comes later**: single panels first, then compose with R (patchwork/cowplot) — the "source-include without hitting disk" hook is in place, and `compose_panels` is scheduled for M4.
