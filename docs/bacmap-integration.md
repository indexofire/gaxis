# bacmap integration

gaxis is designed to be **one tool surface inside bacmap's research workflow**, and a standalone
tool at the same time. This document is the bacmap-side contract; the reference adapter lives in
`integrations/bacmap_upstream_gaxis.py` (repo root, not part of this site).

## 1. Topology

```
bacmap MCP server ──(upstream MCP client)──► gaxis MCP server (Streamable HTTP)
      │                                            │
      └─ LLM sees bacmap_chart_* tools             └─ figure + script + manifest
```

- gaxis runs as its own process (ADR-01/02). bacmap never imports gaxis internals.
- The adapter is thin: mapping, naming, gating. No paper logic, no chart logic, no caching.
- Startup order does not matter: an unreachable gaxis yields a JSON error, never a crashed turn.

## 2. Starting gaxis

```bash
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
gaxis-mcp --transport http --host 127.0.0.1 --port 8770
# client endpoint: http://127.0.0.1:8770/mcp, Authorization: Bearer <token>
```

HTTP refuses to start without a token (fail-closed, same policy as bacmap). `--transport stdio`
exists for local debugging only.

## 3. Wiring the adapter into bacmap

Copy the reference file to `bacmap/src/bacmap/interfaces/mcp/upstream/gaxis.py`, then register it
where the server is assembled:

```python
from bacmap.interfaces.mcp.upstream.gaxis import GaxisUpstream

upstream = GaxisUpstream(
    url=cfg.gaxis.url,  # default http://127.0.0.1:8770/mcp
    token=os.environ["GAXIS_MCP_TOKEN"],
    max_data_class=profile.max_data_class,  # cloud profile → "D1"
)
upstream.register(server)  # returns the registered names
```

`register()` is additive and idempotent per call: every visible tool becomes
`bacmap_chart_<gaxis tool name>` with a `params` input model, matching bacmap's existing legacy-tool
convention (`{"params": {...}}`, schema in `$defs`).

## 4. Data-class gating (the reason this adapter exists)

gaxis tools declare `data_class`:

| gaxis tool | class | what it touches |
|---|---|---|
| `health` | D1 | nothing |
| `search_chart_assets` | D1 | paper corpus |
| `get_chart_manifest` | D1 | paper corpus |
| `reproduce_chart_code` | D1 | paper code in sandbox |
| `describe_data_schema` | D3 | local user table |
| `render_chart_from_data` | D3 | local user table |
| `adapt_chart_code` | D3 | local user table |

Consequences under bacmap's `cloud` profile (ceiling D1): the four D3 tools are **not registered at
all**, so the model cannot even see them, and a direct call is rejected before leaving the process.
Under `local-trusted` (D4) all seven appear.

The gating is deliberately doubled: at registration (visibility) and at call time (defence in
depth). Both fail closed with a JSON error, matching bacmap's own `_register_legacy_tool` pattern.

## 5. Result shape

bacmap handlers return JSON strings; gaxis returns structured content. The adapter stringifies and
keeps gaxis's error convention:

```json
{"error": "...", "code": "unknown_column", "message": "...", "hint": "available columns: [...]"}
```

`code` is the stable kernel error code (`data_not_found`, `unknown_column`, `not_numeric`,
`missing_x`, `missing_y`, `render_failed`, `bad_parameter`), so bacmap can map it to
`suggested_fix`/`recovery_commands` without parsing prose.

## 6. What bacmap should and should not do with it

**Should**

- Use `describe_data_schema` first, then `render_chart_from_data` with explicit `preset` when the
  target journal is known (`nature_microbiology`, `asm`, `isme`, `cell_host_microbe`,
  `microbial_genomics`).
- Treat the returned `code_path` + `manifest_path` as the deliverable: the manifest carries
  `data.sha256` and `code_sha256`, which is what makes a figure auditable in a paper draft.
- Surface `lint.issues` to the user instead of silently accepting warnings.
- Call `health` before a long batch to confirm the R backend is installed (ggplot2 figures need it).

**Should not**

- Cache reproduction results in bacmap; the knowledge base (M3/M4) owns caching and weighting.
- Pass D3/D4 data through a `cloud` profile by widening the ceiling at runtime — the profile is set
  at launch for a reason.
- Re-implement spec inference in bacmap: pass explicit `x`/`y`/`hue` when the model already knows
  the biology, let gaxis infer only when it does not.

## 7. Current behaviour of paper-side tools

Until M1–M4 land, the paper side degrades instead of failing:

| Tool | Today | Later |
|---|---|---|
| `search_chart_assets` | `degraded: true`, empty list, message | M3: vector + graph retrieval over `paper-kb` |
| `get_chart_manifest` | `found: false` | M1: ChartReproManifest |
| `reproduce_chart_code` | `not_implemented: true`, `run_status: "skipped"` | M2: podman sandbox + L1/L2/L3 |
| `adapt_chart_code` | works, `source: "builtin_templates"`, `fallback_reason` explains | M4: `source: "kb_asset"` with `asset_ids` |

This is intentional: a host can wire all twelve tools today and get better answers over time without
changing its own code.

## 8. Failure modes and what they look like

| Symptom | Cause | Response |
|---|---|---|
| `{"error": "gaxis unreachable at ..."}` | server down / wrong port | start gaxis; the adapter preflights TCP so this is immediate |
| HTTP 401 on connect | token missing or mismatched | check `GAXIS_MCP_TOKEN` on both sides |
| `{"error": "... above the profile ceiling ..."}` | D3 tool under a D1 profile | use `local-trusted`, or don't ask for local-data figures |
| `code: "render_failed"` + `hint` (last stderr lines) | generated script errored | full log at `<figure dir>/render.log` |
| `code: "not_numeric"` | `y` points at a categorical column | call `describe_data_schema` and pick a numeric column |
| `code: "unknown_column"` | typo or stale schema | `hint` lists available columns |

## 9. Verification

gaxis keeps the adapter honest with tests that run the real thing:

```bash
pixi run pytest -q tests/test_mcp.py tests/test_bacmap_upstream.py
```

They spawn a real Streamable-HTTP server on loopback, enforce auth, render a figure over MCP, and
assert the profile gating, naming, JSON-string results and error mapping. If you change the adapter,
these are the tests that must stay green.


## Figure handoff: bacmap results → gaxis

bacmap already holds AMR calls, species, serotype and typing. gaxis does not re-run those tools; it
consumes an exported table and produces the figure/evidence.

The reference exporter is `integrations/bacmap_export.py` (stdlib only; imports neither project):

```bash
python integrations/bacmap_export.py --run-dir <bacmap results run> --out data/bacmap-export
# amr_long.csv: sample,gene,gene_class
# metadata.csv: sample,species,serotype
```

Then:

```bash
gaxis analysis run amr-cooccurrence --input data/bacmap-export/amr_long.csv --out data/analysis
gaxis render --chart network --data data/analysis/<run>/edges.csv \
  --x source --y target --weight weight --color-map data/analysis/<run>/palette.json --preset asm
```

The same table contract can be produced by a bacmap query/result tool; the important boundary is
that **only tables cross the boundary**, not raw reads or the database. See tutorial 10 for a real
run (20 Salmonellae, 121 AMR rows → 9-gene/20-edge figure).
