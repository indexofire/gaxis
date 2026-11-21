# FAQ

## Installation and Environment

### Do I have to use pixi?

Recommended. gaxis needs Python 3.12, matplotlib, and R + ggplot2 at the same time; pixi installs all of them in one go and locks the versions.
With other environments, at least make sure you have these dependencies and Python 3.12.

### Can I test without podman?

Yes. Rendering figures, chart selection, adaptation, composition, and KB retrieval do not require podman. For reproduction you can use `--engine local`,
but the report will state that there is no isolation — **do not treat a local run as evidence of safe execution**. For production reproduction, install rootless podman.

### Can I test without gbrain / ollama?

Yes. When `[knowledge] enabled = false` or `GAXIS_KB_ENABLED=false`, retrieval returns `degraded: true`,
and everything else works as usual. The embedding model (bge-m3) only affects semantic retrieval; keyword retrieval still works when ollama is unavailable.

### Should the knowledge base be committed to git?

No. KB pages are rebuilt from the manifest, and `data/` is already in `.gitignore`. On a new machine:

```bash
pixi run gbrain-init
pixi run gaxis kb seed
pixi run gaxis kb ingest
```

## Data

### Which data formats are supported?

Currently delimited text: CSV and TSV (delimiter auto-detected, UTF-8, optionally with a BOM).
Excel / Parquet / JSON are not yet supported; please export to CSV first.

### What if my column names are not in English?

That is fine. Column names are used only as identifiers; figure labels can first be generated from the column names and then changed to Chinese/units in `figure.py`.
Column names in annotations and in `SPEC` must match the table header exactly.

### What about missing values in the data?

During rendering, `""`, `NA`, `n/a`, `nan`, and `None` are recognized as missing; if you need a more complex missing-value strategy, clean the data first before handing it to gaxis,
or change it in the generated script.

## Rendering Figures

### Why does lint report L005 (font fallback)?

The presets require the Arial/Helvetica family; when the system does not have it, they fall back to Liberation Sans and the like. The fallback is written into the lint output,
never silently substituted. Install the fonts or adjust the preset's `font_family`, then rerun.

### Can I modify the generated script?

Yes, and you should — it is a deliverable. Note: once modified, it no longer matches the manifest's `code_sha256`;
if you want to preserve the evidence chain, sync the changes into the template or re-render.

### Why is the `figure_id` the same when rendering the same data twice?

`figure_id` is determined by `PIPELINE_VERSION + data hash + spec`; the determinism is intentional. Changing the preset, the columns, or the data changes it.

## Chart Selection and Knowledge Base

### How long does `kb seed` take?

7 presets × 6 chart types × 2 backends = 84 templates, about 2.5 minutes on a local machine, works offline, idempotent.

### Why can't templates be found in retrieval?

`search_chart_assets` only queries `type: analysis` (paper figures) by default. Templates are also not returned by ordinary `kb search` queries;
this is by design: templates are resolved via the exact slug in `adapt`, not mixed into paper candidates.

### Does the order of figures in the contact sheet not match the terminal?

The sheet is numbered by return order (`#1…`), and the terminal uses the same order. If the order differs, check whether you used filters such as `--tier`/`--has-code`
(filtering happens server-side; both sides should be consistent).

## Reproduction

### What does `needs_data` mean?

The script needs to read a table, but you provided no `--data` and did not enable `--synthetic`. This is not a failure; it is a clearly identified input gap.

### What does `needs_env` mean?

The sandbox image is unavailable (podman missing, build failed, pull failed). See `sandbox_report.notes`.

### Why do most real papers not reach L1?

Two common reasons: the paper's repository may not include the raw data; unlocked dependencies cause the build to fail. gaxis states the tier and the explanation explicitly,
and never passes off "it ran" as "it reproduced".

### Why didn't the tier in the KB change after reproduction?

Only paths that go through `reproduce_chart_code` refresh automatically. After manually editing the manifest, run `pixi run gaxis kb ingest`.

### Why can't GPL code go into templates?

Licensing is a gate: copyleft code can be recorded (to understand its logic), but it is never copied into templates or executed in the sandbox.
This is a product rule, not a bug.

## MCP / Host

### Why can't the server start without a token?

Production transports must carry a Bearer token (ADR-02). `stdio` is only for local debugging.

### Why doesn't the host see D3 tools?

The host filters `data_class` by profile. The cloud profile only allows D1; `render`/`adapt`/`compose` are D3.

### How to upgrade when the tool contract changes?

The contract version is in `scripts/freeze_contract.py`, and the snapshot is in `tests/contract_snapshot.json`.
Changing the contract requires: bumping the version, refreshing the snapshot, updating `docs/mcp-tools.md`, and writing a changelog.

## Development

### How do I run all checks?

```bash
pixi run check        # ruff + format check + mypy + pytest
pixi run test         # tests only
pixi run docs-build   # build this site (strict)
```

### Do tests touch the real knowledge base?

No. An autouse fixture sets `GAXIS_KB_ENABLED=false`; tests that need the KB use `tests/fake_gbrain.py`.
When writing tests, do not shell out to the real `gbrain`.
