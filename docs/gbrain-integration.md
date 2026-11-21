# gbrain integration (verified on 2026-11-18)

gbrain is installed in this environment and the integration surface has been exercised end to end.
Everything below is a command that was actually run, with its observed behaviour — not a design
sketch. Version: **0.60.740.0** (upstream `master`, `vendor/gbrain`).

## 1. Install (managed by pixi, nothing written to `~/.gbrain`)

```bash
pixi run gbrain-install     # vendor the repo, bun install, write the env shim
pixi run gbrain-init        # create the brain (PGLite, no embeddings)
pixi run gbrain --version   # gbrain 0.60.740.0
pixi run gbrain doctor      # 100/100 except sync_freshness (see §6)
```

Where things live:

| Path | What | Tracked |
|---|---|---|
| `vendor/gbrain` | upstream checkout (`git`, `bun install`) | gitignored |
| `vendor/bun` | pinned bun **1.4.4** — gbrain refuses older; conda-forge ships 1.4.2 | gitignored |
| `.pixi/envs/default/bin/gbrain` | shim → `scripts/gbrain.sh` | env |
| `${XDG_DATA_HOME:-~/.local/share}/gaxis/gbrain` | brain DB (`GBRAIN_HOME`) | no |
| `~/.local/share/gaxis/paper-kb` | source root: canonical page files | no |

`scripts/gbrain.sh` exports `GBRAIN_HOME`, so the brain is per-user and **outside any git
worktree** — gbrain refuses to own a content directory inside a repository (`local_conflict`), and
a brain next to source code is one `git add -f` away from being committed (`home_dir_in_worktree`).

## 2. Isolation: `federated=false` exists and works

```bash
pixi run gbrain sources add paper-kb \
  --path ~/.local/share/gaxis/paper-kb --no-federated --force --json
# {"id":"paper-kb", …, "federated":false}
# "federated: false — only searched when explicitly named via --source"
```

This is plan ADR-04 implemented literally: `paper-kb` is invisible to a search that does not name
it. Two hard rules learned the hard way:

1. **The source path must be outside the repository worktree.** A path inside it is claimed as the
   canonical worktree and every write/sync is refused (`writer_coordinator_required`,
   `recovery_required`).
2. **A source id cannot be re-pointed at a new path.** `sources add` on an existing id fails; you
   must `sources remove <id> --confirm-destructive` (deletes its pages) and re-add.

## 3. Write path: `put` / `delete`, revision-guarded

```bash
pixi run gbrain put paper-kb:smoke-0001 \
  --content-origin tool_output --reason "gaxis ingest" < examples/paper-kb-page.example.md
pixi run gbrain put paper-kb:smoke-0001 --expected-revision <rev> …   # correct update
pixi run gbrain put paper-kb:smoke-0001 --force …                      # deliberate re-ingest
pixi run gbrain delete paper-kb:smoke-0001 --expected-revision <rev>   # or --force
```

Observed semantics (all verified):

| Scenario | Result |
|---|---|
| new page | created; `put` writes a canonical `.md` file into the source root **and** the DB |
| existing page, no revision | `revision_required` — writes are optimistic-concurrency, never blind upsert |
| `--force` | replaces regardless; used by gaxis for deterministic re-ingest |
| `delete` | `soft_deleted` (recoverable), page leaves `list`/`search` |
| paper-derived content | must pass `--content-origin tool_output` — gbrain then treats it as untrusted input |
| `--request-id` | reuse **only** to retry the identical request |

`gbrain sync --source paper-kb` is **not** usable for us: it needs git/writer-coordinator
activation (`writer_coordinator_required`), and claiming a nested worktree is refused. gaxis writes
pages explicitly, which is also what makes re-ingest idempotent.

## 4. Read path: filtering, not just text

```bash
pixi run gbrain search "rarefaction curve" \
  --source-id paper-kb --types analysis --where chart_type=line --limit 5 --json
pixi run gbrain query "<question>" --expand        # hybrid + LLM expansion (costs tokens)
pixi run gbrain get paper-kb:smoke-0001 --json     # includes `revision`
pixi run gbrain call get_health '{}'               # engine health (wedged/declined/skipped)
```

- `--where key=value` is **frontmatter equality**: this is how gaxis filters on `chart_type`,
  `reproduction_level`, `preset_hint` — the filters ADR-10 needs. Verified working.
- `--types` filters the declared page type; `--source-id` scopes to the isolated source.
- With embeddings disabled the result carries `degraded: embed_unavailable`; keyword search still
  returns the page. gaxis must surface that flag rather than treating a thin result as "not found".
- `get --json` returns `revision` — store it (SQLite) if you want revision-guarded updates instead
  of `--force`.

## 5. Page types must be declared

`put` with `type: chart-asset` was rejected: the active schema pack declares 25 types
(`analysis`, `code`, `concept`, `event`, …). Verified working: **`type: analysis`** for figure
pages. Plan for M3: `analysis` for figures, `code` for extracted scripts; a custom
`chart-asset` type would require shipping a schema pack (`~/.gbrain/schema-packs/`) — not worth it
until we need type-specific relations.

## 6. Health: one expected FAIL

`gbrain doctor` reports `sync_freshness` FAIL for `paper-kb` because the source is write-through
(`put`) and never `sync`ed. This is a consequence of the supported write path, not a broken install:
everything else scores OK. `pixi run gbrain-doctor` wraps the check: it prints the full report and fails only on
**unexpected** FAILs, so `sync_freshness` for a write-through source does not mask a real problem.

## 7. Multimodal: what gbrain does and does not need to do

Decision framing (the user's proposal): **the KB stores reproduction code and metadata; images stay
as files in a directory with a manifest mapping; when a multimodal host wants to look at a figure it
opens the path — gbrain is never asked to "see" it.**

That is the right default, and it is sufficient for:

| Query | Mechanism |
|---|---|
| "find reusable code for a rarefaction curve" | text search over caption + visual grammar + code |
| "which stories have grouped bars with error bars?" | `--where chart_type=bar` + text |
| "show me the original figure" | host opens `image_path` from the manifest/page |
| "same visual style as this paper's Fig. 3" | text search on `visual_grammar` + `preset_hint` |

It is **not** sufficient for retrieval *by image* ("here is a screenshot, find similar figures") —
that needs an image embedding space. Two upgrade paths exist, both pluggable behind one
`VisualIndex` port:

1. **gbrain-native multimodal embeddings.** gbrain 0.60 accepts
   `--embedding-model voyage:voyage-multimodal-3` at init (`embeddings enable` can switch in place).
   One vector space for images **and** text; paid API; requires re-embedding everything and sending
   figure images to a third party — a data-policy question for bacmap profiles.
2. **Local CLIP index.** ~1 GB model on CPU, free and offline, stored as a numpy matrix next to
   SQLite; fused with the text results in `kb/retrieve.py`. No new service, no external call.

Recommendation: stay text-only at M3, and make `visual_grammar` a first-class text field at ingest
(chart type, encoding roles, palette, axis/legend style, panel layout, journal preset, similarity
score). Add path 2 only if a real "find figures that look like this image" use case appears.
Searching for a different KB product is **not** warranted: gbrain already covers text + code +
metadata filtering + source isolation; image embedding is a ~150-line local index, not a reason to
migrate.

Cheap wins worth doing regardless:

- perceptual hash (pHash) at ingest → duplicate/near-duplicate figures do not pollute retrieval;
- keep `image_path` relative to the asset root and resolve through `asset_id`, so moving the data
  directory does not break every page;
- the manifest is authoritative; gbrain pages are a **derived, rebuildable index** (safe to wipe and
  re-ingest, which is exactly what `--force` is for).

## 8. What gaxis implements (M3, done)

| Piece | Plan |
|---|---|
| `kb/gbrain.py` | `KnowledgeBase` port impl over the CLI: `put_page`, `get_page`, `delete_page`, `search`, `status` |
| `kb/pages.py` | `ChartReproManifest` → markdown page (`type: analysis`, frontmatter = filterable facts, body = caption + visual grammar + code summary + relative paths) |
| `kb/ingest.py` | content hash per asset in `data/kb/state.json`; skip unchanged; `--force` rewrites; auto-ingest after a full paper ingest |
| `kb/search.py` | chunk hits → one asset per page; level/preset filtering and ranking; chart-type fallback |
| config | `[knowledge] enabled, source, binary, gbrain_home, types, auto_ingest, timeout_s, retries`; env `GAXIS_KB_ENABLED`, `GAXIS_GBRAIN_BIN`, `GAXIS_GBRAIN_HOME` |
| failure mode | gbrain missing/busy → `search_chart_assets` returns `degraded: true` + reason |

## 7b. Local embeddings: measured on this machine (2026-11-19)

Installed user-level (`~/ollama`, systemd user unit, `OLLAMA_KEEP_ALIVE=10m`), model `bge-m3`
(1.2 GB, 1024-dim). Brain switched with:

```bash
gbrain embeddings enable --embedding-model ollama:bge-m3   # keeps pages/facts, queues chunks
gbrain embed --stale                                      # 11 chunks across 10 pages
pixi run gaxis kb status                                  # missing_embeddings: 0
```

Measured (Intel Core Ultra 7 255H, 16 cores, no GPU, ~1000-character chunk):

| Metric | bge-m3 | nomic-embed-text (comparison) |
|---|---|---|
| dimensions | 1024 | 768 |
| model size | 1.2 GB | 274 MB |
| cold start (load + embed) | ~3.5 s | ~1.0 s |
| warm embed per chunk | **~1.43 s** | ~0.36 s |
| memory (llama-server RSS) | **~1.4 GB** | not measured |
| CPU during embed | ~170 % (llama-server), `OLLAMA_NUM_THREADS=8` made no difference | — |
| our scale | 11 chunks = **29 s** total (includes per-call overhead) | — |

bge-m3 is ~4× slower than nomic here and memory-bound, but it is multilingual — which is the
reason to keep it: a Chinese query with no keyword overlap now works:

```
before (keyword only): gaxis kb search "稀释曲线" (Chinese: rarefaction curve) → 0 hits
after  (bge-m3):       gaxis kb search "稀释曲线" (Chinese) → 3 hits (rarefaction figures)
```

Cost control: `OLLAMA_KEEP_ALIVE=10m` in the unit file (set `0` to unload immediately);
`systemctl --user disable --now ollama` turns semantic search off, and gbrain degrades to
`embed_unavailable` (keyword still works, `degraded` is surfaced by gaxis).

## Open questions that remain (none block M3 scaffolding):

1. Enable local embeddings (`ollama:bge-m3`) or stay keyword-only until the first retrieval-quality
   measurement? Keyword-only makes "find similar" weak; a local embedding model is free but needs
   Ollama on the host.
2. If/when image retrieval is required: local CLIP (offline) or `voyage-multimodal-3` (paid, and
   figure images leave the machine — relevant to bacmap's cloud profile ceiling)?
3. Do we ever want `gbrain think` (multi-hop synthesis)? It needs an LLM key and produces prose;
   gaxis's own adaptation path does not need it.

## 9. Quick reference

```bash
pixi run gaxis kb status
pixi run gaxis kb ingest --force
pixi run gaxis kb search "rarefaction curve" --min-level L2 --json
pixi run gbrain sources list --json
pixi run gbrain search "growth curve" --source-id paper-kb --where reproduction_level=L1 --json
pixi run gbrain get paper-kb:<asset_id> --json | jq .revision
pixi run gbrain put paper-kb:<asset_id> --force --content-origin tool_output --reason "re-ingest"
pixi run gbrain delete paper-kb:<asset_id> --force
pixi run gbrain doctor
```
