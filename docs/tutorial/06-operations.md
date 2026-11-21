# 06 Operations: Queues, Scheduling, and Self-Healing

## Goals

Let the knowledge base grow automatically while ensuring that failures are visible, progress is recoverable, and evidence is verifiable.

Every operation in this section is idempotent: interruptions, reruns, and concurrent triggers never redo work that is already done.

## 1. Checkpoint Queue

```bash
# ingestion job
pixi run gaxis ops enqueue 10.1099/mgen.0.000001 paper.pdf --mode full

# reproduction job (source is a paper id)
pixi run gaxis ops enqueue --kind reproduce pdf-0883b2ad

pixi run gaxis ops run --limit 5 --retries 2
pixi run gaxis ops status
```

The queue lives in `data/ops/queue.db` (SQLite); each row is one source:

| Field | Meaning |
|---|---|
| `status` | `pending` / `running` / `done` / `failed` |
| `kind` | `ingest` / `reproduce` |
| `attempts` | Number of attempts so far |
| `last_error` | Reason for the last failure (truncated to 500 characters) |
| `manifest_ids` | Manifests produced by this source — the evidence |
| `updated_at` | Checkpoint timestamp |

Behavior contract:

- **Each source is an independent checkpoint**: after a crash and restart, only unfinished work is resumed;
- **`done` entries are never rerun** (deduplicated by the source string, using the canonical DOI/paper id);
- **Only transient failures are retried** (`resolution_failed`, `download_failed`, `pdf_unreadable`);
- **Permanent failures** (`unrecognised_source`, etc.) stay in `failed` and require an explicit `status --reset`.

## 2. Stall Reclamation and Heartbeat

At the start of every run, `ops run`:

- reclaims `running` jobs that have been stuck for longer than `--stall-minutes` (default 30) back to `pending` — self-healing after a killed process;
- after finishing, writes `data/ops/heartbeat.json`:

```json
{"finished_at": "2026-11-21T12:40:03+00:00", "duration_s": 42.1,
 "processed": ["10.1099/mgen.0.000001"], "failed": [],
 "reclaimed": 0, "queue": {"done": 1}}
```

`ops status` shows the last run.

## 3. Deep Verification: Is the Evidence Still There?

```bash
pixi run gaxis ops verify
```

It checks whether the `manifest_ids` of every `done` job still exist and can be parsed; if evidence is lost (e.g. `data/` was wiped or a restore failed), the job is requeued with the reason:

```
checked 1 done job(s); missing 0 manifest(s); requeued 0
```

!!! warning "`done` does not mean complete"
    A `done` without manifests is a fake state. It is `verify`'s job to correct it, not to cover it up.

## 4. Scheduled Runs

The queue has no resident daemon; a systemd user timer is all you need:

```ini
# ~/.config/systemd/user/gaxis.timer
[Unit]
Description=gaxis ingestion queue every 6 hours

[Timer]
OnBootSec=15min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# ~/.config/systemd/user/gaxis.service
[Unit]
Description=gaxis ingestion queue

[Service]
Type=oneshot
WorkingDirectory=%h/repos/github/gaxis
ExecStart=%h/.pixi/bin/pixi run gaxis ops run --limit 10 --retries 2
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now gaxis.timer
systemctl --user list-timers gaxis.timer
```

`Persistent=true` makes a run missed because of a shutdown catch up once after boot; `--limit` caps the duration of each run so timers do not pile up.

## 5. Health Check (Read-Only)

```bash
pixi run gaxis health
pixi run gaxis-mcp --transport http --port 8770   # hosts can poll the health tool
```

`health` does not render, download, lock, or write any files, so it is safe to use as a liveness probe and for clock-skew checks.

## 6. Environment Variable Quick Reference

| Variable | Purpose |
|---|---|
| `GAXIS_DATA_DIR` | Data root directory (default `./data`) |
| `GAXIS_CONFIG` | Configuration file path |
| `GAXIS_SANDBOX_BACKEND` | `podman` or `local` |
| `GAXIS_KB_ENABLED` | Turn off the knowledge base (testing/offline) |
| `GAXIS_GBRAIN_HOME` | gbrain data directory |
| `GAXIS_MCP_TOKEN` | Bearer token for the MCP server (required) |

For the full list, see the [configuration reference](../reference/configuration.md).

## 7. Logs and Troubleshooting

- Rendering: `<figure-dir>/render.log` (stdout/stderr/exit code);
- Reproduction: `data/repro/<asset>/<sha8>/reproduction.json` (grading, similarity decomposition, sandbox report);
- Queue: `data/ops/queue.db` (query directly with `sqlite3`);
- Heartbeat: `data/ops/heartbeat.json`;
- Selection feedback: `data/kb/selections.jsonl`.

## Checklist

- [ ] Enqueueing the same source twice with `ops enqueue` returns `0 new … already known` the second time;
- [ ] After killing a running `ops run`, the next run reports `reclaimed 1` and continues;
- [ ] `ops verify` requeues a job after its manifest is deleted;
- [ ] The `queue` counts in `heartbeat.json` match `ops status`.

## Common Issues

**Timer never fires**: run `systemctl --user status gaxis.timer` and check `NextElapse`; the user needs `loginctl enable-linger` for it to run while logged out.

**Queue stuck in running but the process is gone**: the next `ops run` reclaims it automatically; if you need it urgently, use `ops status --reset <source>`.

**gbrain lock timeout**: `gbrain embed` or another gbrain process holds the database lock. Wait for it to finish; do not delete the lock file.
