# Operations: ingestion queue and composition

## 1. Checkpointed paper ingestion (`gaxis ops`)

```bash
pixi run gaxis ops enqueue 10.1099/mgen.0.000001 10.1371/journal.pone.0000217 paper.pdf
pixi run gaxis ops run --limit 5 --retries 2 --stall-minutes 30
pixi run gaxis ops status            # counts, last errors, last run
pixi run gaxis ops verify            # requeue done jobs whose manifests vanished
pixi run gaxis ops status --reset all   # requeue failed jobs
```

- Queue lives in `data/ops/queue.db` (SQLite): `source`, `mode`, `status`
  (`pending|running|done|failed`), `attempts`, `last_error`, `manifest_ids`.
- Each source is its own checkpoint. A crash or a network failure resumes from the queue; a
  `done` source is never re-ingested (dedupe by source string — use canonical DOIs/ids).
- Retries are bounded and only for transient failures (`resolution_failed`, `download_failed`,
  `pdf_unreadable`); a permanent failure (`unrecognised_source`, …) goes to `failed` and stays there
  until `--reset`.
- Successful runs return `manifest_ids`, which are also recorded in the queue row, so a later step
  can verify what was produced even if the KB is rebuilt.
- **Stall recovery**: a job left in `running` by a killed process is returned to `pending` on the
  next run once it is older than `--stall-minutes` (default 30). That is what makes the timer safe
  to use without a daemon.

### Running it on a timer

The queue is safe to run from a systemd timer (no daemon state, one process per run):

```ini
# ~/.config/systemd/user/gaxis-crawl.service
[Unit]
Description=gaxis paper ingestion queue

[Service]
Type=oneshot
WorkingDirectory=%h/repos/github/gaxis
ExecStart=%h/.pixi/bin/pixi run gaxis ops run --limit 10 --retries 2
```

```ini
# ~/.config/systemd/user/gaxis-crawl.timer
[Unit]
Description=Run gaxis ingestion every 6 hours

[Timer]
OnBootSec=15min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now gaxis-crawl.timer
systemctl --user list-timers gaxis-crawl.timer
```

Self-healing today:

- **stall detection**: a `running` job older than `--stall-minutes` returns to `pending`;
- **heartbeat**: every run writes `data/ops/heartbeat.json` (finished_at, duration, processed,
  failed, reclaimed, queue counts); `gaxis ops status` shows the last run;
- **deep check**: `gaxis ops verify` re-checks every `done` job's manifests and requeues sources
  whose evidence disappeared (cleaned `data/`, failed restore). A `done` job with no manifest is a
  lie, so it is corrected, not hidden.

### Reproducing a paper's figures

```bash
pixi run gaxis reproduce-paper pdf-<sha8>                 # suitable figures, best code first
pixi run gaxis reproduce-paper pdf-<sha8> --data table.csv
pixi run gaxis reproduce-paper pdf-<sha8> --synthetic     # labelled synthetic input
pixi run gaxis ops enqueue --kind reproduce pdf-<sha8> && pixi run gaxis ops run
```

- Suitability: a figure needs a code candidate at/above `--min-confidence` (default 0.5); already
  graded L1/L2 figures are skipped unless `--force`.
- Outcomes are explicit: `reproduced`, `needs_data` (script asked for a table), `needs_env` (sandbox
  image unavailable), `skipped` (no code / low confidence), `failed`.
- Synthetic input is generated from the columns the script indexes and recorded as
  `data_source: synthetic`; a figure built that way proves the code runs, not the paper's numbers.
- Every reproduced script is copied into `data/assets/code/…` and its manifest page is refreshed in
  the KB, so retrieval sees the new level immediately.

## 2. Seeding verified templates (`gaxis kb seed`)

`adapt_chart_code` reuses the *plotting code* of a verified template, so the KB needs at least one
lint-clean asset per `(preset, chart type, backend)`:

```bash
pixi run gaxis kb seed                                  # all presets, python + R (~2.5 min)
pixi run gaxis kb seed --preset asm --backend python    # narrower
pixi run gaxis kb seed --force                          # rewrite pages even if unchanged
```

- Each template is a real render: emitted script, PDF, lint report and manifest, produced by the same
  pipeline users get. A template whose lint is not clean is reported as failed, never indexed.
- The script is copied to `data/assets/templates/<preset>/<chart>-<backend>/figure.<py|R>` and the
  page stores `code_path`, `code_sha256`, `reproduction_level: L1` and `type: template`.
- Pages are `type: template`, so `search_chart_assets` (which asks for `type: analysis`) never returns
  them; adaptation resolves them by exact slug.
- Re-running is idempotent: unchanged code hashes are skipped, changed templates are rewritten.
- Seeded figures are not paper evidence: their reproduction level is L1 because the pipeline
  reproduces them byte-for-byte, not because a paper was sandboxed.

## 3. Adopting paper scripts (`gaxis kb adopt`)

`adapt_chart_code` can reuse a reproduced paper script, but only under an explicit, checkable
interface: the script must read its input through `DATA_PATH` (Python assignment / R `<-`).

```bash
pixi run gaxis kb adopt pdf-<sha8>/fig-1 --code path/to/script.py --preset asm
pixi run gaxis adapt --data my.tsv --asset template:paper-pdf-<sha8>-fig-1 --preset asm
```

- Adoption never runs the code; it copies it to `data/assets/templates/paper/<id>/` and records
  `origin: paper`, `interface: path`, `source_asset`, licence and reproduction level.
- Adaptation rewrites only `DATA_PATH` (and `OUT_DIR` when the script declares one), then runs the
  script in an isolated output directory and collects whatever figure files it writes.
- A script without a `DATA_PATH` binding is refused (`adoption_refused`) — gaxis will not guess at
  a research codebase's I/O. Column names remain the paper's; map your table first.
- The column/encoding mismatch is reported by the run itself (`render_failed` with the traceback),
  never papered over.

## 4. Multi-panel composition (`gaxis compose`)

Panels are rendered first, each with its own script and manifest. Composition arranges the finished
**PDFs** (no re-render), so the vector content survives and every panel keeps its evidence
(`code_sha256` recorded in `CompositionManifest`).

```bash
pixi run gaxis compose --panels bar-<id>,line-<id> --layout 1x2 \
  --preset nature_microbiology --out data/demo/composition
```

- Panels are figure ids (as printed by `render`) or paths to a panel's `manifest.json` — the id
  resolves under `data/renders` and anywhere in the data root, so custom `--out` directories work.
- Layout: `ROWSxCOLS` or automatic (1×n for ≤3, 2×2 for four, grid otherwise).
- Page size defaults to the preset's double-column width; `--width/--height` override (mm).
- Panel letters A/B/C are added when `--labels` (default on).
- Output: `composition-<id>.pdf` (+ `.png` preview) and `composition-<id>.json`
  (`CompositionManifest` with panel ids, labels, code hashes, geometry, lint).
- `--uniform` re-renders each panel from its manifest at the composition preset and the cell size,
  so type sizes and line weights match across panels. Without it, panels are placed as rendered.
- Lint runs on the composition output, so geometry/font problems show up here as well.
- Limitation: mixed backends are fine (both emit PDF), but panels must be **vector**; a PNG-only
  panel is rejected with `panel_not_vector`.
