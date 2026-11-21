# integrations/

Reference implementations that belong to **other** repositories but are kept here so they are
tested against the real kernel (`tests/test_bacmap_upstream.py` spawns a live MCP server).

| File | Destination | Purpose |
|---|---|---|
| `bacmap_upstream_gaxis.py` | `bacmap/src/bacmap/interfaces/mcp/upstream/gaxis.py` | exposes gaxis as `bacmap_chart_*` tools, enforces bacmap's data-class ceiling |

**Status: installed.** The live copy lives in the bacmap repository at
`src/bacmap/interfaces/mcp/upstream/gaxis.py` (with `build_upstream(profile)` and env gating); this
file is the upstream reference kept under test in `tests/test_bacmap_upstream.py`.
Design and behaviour: [`docs/bacmap-integration.md`](../docs/bacmap-integration.md).

Rules for anything added here:

- ≤150 lines, no business logic, no caching;
- must be covered by a test in `tests/` that runs against the live server fixture;
- if it needs a change in the host repository, document it in the module docstring as a copy-paste
  recipe.
