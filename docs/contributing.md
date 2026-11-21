# Contributing

`AGENTS.md` at the repository root contains the complete development rules; only the most commonly used ones are listed here.

## Environment

```bash
pixi install
pixi run check      # must be green before committing
pixi run fmt
```

## Five Hard Rules (violating them requires writing a decision first)

1. **Tool contracts are frozen**: 10 MCP tools (v2.1). Changing names/inputs/outputs requires bumping the version, refreshing
   `tests/contract_snapshot.json` (`pixi run python scripts/freeze_contract.py`), and updating
   `docs/mcp-tools.md` and `docs/service-flows.md`.
2. **core does not import host SDKs**: there is no bacmap/Pi/DSH in `models/spec/style/render/exec/service.py`.
3. **Host adapters are thin**: ≤150 lines, no business logic, no importing each other.
4. **Generated code does not import gaxis**: `figure.py` / `figure.R` must be able to run standalone.
5. **Every render writes a manifest**: `data.sha256`, `code_sha256`, outputs, lint — not one can be missing.

Other key conventions:

- Dual-backend parity: any chart-type capability is provided in both matplotlib and ggplot2, otherwise it does not ship;
- No silent degradation: missing fonts, missing presets, fallback backends, skipped sandboxes must show up in lint or the manifest;
- `health` is read-only;
- Every tool declares its `data_class`;
- No LLM calls in the rendering path;
- Paper code runs only in the sandbox; cloned code is never executed during ingest.

## Adding a Feature

1. First review the contracts in `DESIGN.md` and `docs/service-flows.md`;
2. Data models go in `models/` (bare dicts are not allowed across modules);
3. Failures use `GaxisError(code, message, hint)`, where code is a stable string;
4. New behavior needs tests: end-to-end for rendering, unit tests for inference/lint;
5. Both Python and R must produce output (for new chart types);
6. Update the docs along with it: this page, `docs/mcp-tools.md`, `CHANGELOG.md`.

## Changing the Contract

```bash
# 1. change the models/tool signatures and the version
# 2. refresh the snapshot
pixi run python scripts/freeze_contract.py
# 3. update the matching section and version table in docs/mcp-tools.md
# 4. write the CHANGELOG entry
pixi run check
```

## Documentation

The site is bilingual and built with MkDocs Material + `mkdocs-static-i18n` in **suffix** mode:

```
docs/page.md        English (default)
docs/page.zh.md     Simplified Chinese
```

```bash
pixi run docs-serve      # preview at http://127.0.0.1:8000/gaxis/ (English) and /gaxis/zh/
pixi run docs-build      # strict build: broken links/nav/translations fail
```

Rules when adding or editing a page:

1. Add **both** `page.md` and `page.zh.md`; never leave one language falling back silently.
2. Add the page to `nav` in `mkdocs.yml` and add its title to `plugins.i18n.languages[zh].nav_translations`.
3. Links inside `.zh.md` pages point at `other.zh.md`; links inside English pages point at `other.md`.
4. Images live in `docs/assets/` and are referenced with the absolute project path
   `/gaxis/assets/…`, which resolves in both languages and in local preview (the site is served
   under `/gaxis/`).
5. Commands in the docs must be directly executable — do not write parameters that do not exist.
