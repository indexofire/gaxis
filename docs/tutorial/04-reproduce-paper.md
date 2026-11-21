# 04 Paper Reproduction → Code Ingestion

## Goal

Turn a paper into searchable, reproducible, reusable assets: parse figures and captions → find code → run in a sandbox → grade by visual comparison →
**automated script assetization** → KB page refresh → (optional) register as a template.

This section requires network access and podman.

## 1. Ingest a paper

```bash
# local PDF
pixi run gaxis ingest examples/demo/paper.pdf --mode full

# DOI / arXiv / PubMed / PMC
pixi run gaxis ingest 10.1099/mgen.0.000001 --mode full
```

`--mode kb_first` only parses figures and captions; `--mode full` also downloads the open-access PDF, finds code repositories, clones them, and picks plotting scripts.

The output is a list of manifests:

```
paper: pdf-0883b2ad
manifests: pdf-0883b2ad/fig-1, …
kb: 12 upserted, 0 failed
```

## 2. See which figures a paper has, and which have code

```bash
pixi run gaxis manifest pdf-0883b2ad/fig-1 --json
```

Key fields:

```json
{"code_candidates": [{"code_path": "…", "pairing_confidence": 0.82, "license": "MIT",
                      "packages": ["matplotlib==3.8", "seaborn"]}],
 "reproduction": {"level": "none", "sandbox_run_status": "skipped"},
 "usefulness": {"score": 0.71}}
```

`packages` comes from the repository's `requirements.txt` / `environment.yml` / `DESCRIPTION`, and is used to build per-paper images.

## 3. Reproduce one figure (single figure)

```bash
# use the code found during parsing; a missing table is reported explicitly
pixi run gaxis reproduce pdf-0883b2ad/fig-1 --code figure.py --engine podman

# provide the input table
pixi run gaxis reproduce pdf-0883b2ad/fig-1 --code figure.py --data my_table.csv
```

```
manifest: pdf-0883b2ad/fig-1
engine:   podman   run: success   level: L1
similarity: 0.93
```

The `local` engine is available for development, but the report will state `network_enforced: false, read_only_root: false`;
**do not treat it as evidence of safe execution**.

## 4. Reproduce a paper in batch

```bash
pixi run gaxis reproduce-paper pdf-0883b2ad
pixi run gaxis reproduce-paper pdf-0883b2ad --data table.csv
pixi run gaxis reproduce-paper pdf-0883b2ad --synthetic --min-confidence 0.6
```

It picks figures by code-pairing confidence and reports an explicit status:

| Status | Meaning | Your action |
|---|---|---|
| `reproduced` | Ran successfully; see the level in parentheses | Check the similarity and decide whether to adopt |
| `needs_data` | The script needs an input table, but none was provided | Use `--data` or `--synthetic` |
| `needs_env` | The sandbox image is unavailable | Check podman / dependencies, or switch to `--engine local` for structural validation only |
| `skipped` | No code, or confidence below threshold | Pick a different figure, or lower `--min-confidence` |
| `failed` | The code ran but failed (exception/timeout/blocked) | Check `failure_reason` |

## 5. What happens automatically after a successful reproduction

A successful reproduction does four things:

1. **Script assetization**: copied to `data/assets/code/<asset>/<sha8>/figure.py`; the manifest candidate points to this copy
   and carries `code_sha256`;
2. **manifest update**: `reproduction.level / visual_similarity / failure_reason / data_source / environment_lock`;
3. **KB page refresh**: the page is re-projected within the same call, `sandbox_report.kb_refresh = "refreshed"`;
4. **Searchable**: the new level and similarity are immediately visible in `kb search`.

To verify:

```bash
pixi run gaxis kb search "bar chart expression" --k 3
# pdf-0883b2ad/fig-1   bar   L2   sim=0.775
```

## 6. Turn a reproduced script into a template

```bash
pixi run gaxis kb adopt pdf-0883b2ad/fig-1 --code data/assets/code/pdf-0883b2ad__fig-1/<sha8>/figure.py
```

Adoption has an explicit interface contract: the script must bind its input through `DATA_PATH` (Python assignment / R `<-`).
If it does not, adoption is refused:

```
{"code": "adoption_refused", "message": "the script does not bind its input through DATA_PATH",
 "hint": "expose the input file as DATA_PATH (and optionally OUT_DIR) and adopt again"}
```

After adoption:

```bash
pixi run gaxis adapt --data my.csv --asset template:paper-pdf-0883b2ad-fig-1 --preset asm
```

Adaptation changes only `DATA_PATH` (plus any `OUT_DIR` the script declares), then runs it and collects the figures it writes out. The column names are still the paper's,
so map your table first — this is deliberate: gaxis does not guess research semantics.

## 7. No data: synthetic inputs

```bash
pixi run gaxis reproduce-paper pdf-0883b2ad --synthetic
```

gaxis generates a deterministic table from the column names the script actually indexes, and records `data_source: synthetic`.

!!! warning "What synthetic data proves"
    It proves that **the code runs and the structure matches**; it **cannot** support conclusions of "data-level reproduction". Do not use synthetic-data results
    to claim numeric reproduction at L1.

## 8. Queuing

```bash
pixi run gaxis ops enqueue --kind reproduce pdf-0883b2ad
pixi run gaxis ops run --limit 5
pixi run gaxis ops verify
```

The queue checkpoints, retries, and reclaims stalled jobs (see Section 06).

## Checklist

- [ ] `manifest.reproduction.level` matches what you saw;
- [ ] the script is present in `data/assets/code/...` and its `code_sha256` matches the manifest;
- [ ] `kb_refresh` is `refreshed` or `unchanged` (not `failed`);
- [ ] `kb search` can rank it by the new level;
- [ ] the adopted template page has `origin: paper` and `interface: path`.

## Common issues

**`needs_data` even though the paper repository clearly contains data**: for now you must explicitly pass `--data`; in-repository data discovery is not wired up yet.
Use `--synthetic` to validate the code first, or point manually to the files in the repository.

**`needs_env`**: the per-paper image build failed or podman is unavailable. Check `sandbox_report.notes`; it will tell you whether it was a build failure,
a pull failure, or a missing image.

**`reproduce` was blocked (`level: none`)**: the static scan found dangerous calls, or the license is GPL/AGPL. This is a result, not an error:
the manifest records the reason.

**KB still shows the old level after reproduction**: only paths that go through `reproduce_chart_code` refresh automatically; if you edited the manifest by hand,
re-run `pixi run gaxis kb ingest`.
