# 07 LLM reconstruction (no runnable author code)

## Goal

When a paper has **no public code**, or the code no longer runs (dependency drift, missing data),
still get a figure close to the published one — with an explicit record that a model wrote it, not
the authors.

!!! warning "This is not author-code reproduction"
    `reproduce` runs the authors' script. `reconstruct` asks a vision model to write a new script,
    then judges it with the same sandbox and comparator. The manifest records
    `reproduction.method = llm_reconstruction` (or `llm_repair`), the model name and each round's
    similarity; the KB ranks author reproductions first at the same level.

## When to use it

| Situation | Command |
|---|---|
| No code candidate, or `pairing_confidence` too low | `reconstruct` |
| Code runs but visual similarity is low (L3) | `reconstruct --repair` (starts from the author script) |
| Code fails (imports, version drift, missing data) | `reconstruct --repair` |
| Batch: fill the gaps for a whole paper | `reproduce-paper --reconstruct-missing` |

## Configure the model

Empty fields inherit `[design]`, so one vision endpoint configures both:

```toml
[reconstruct]
enabled = true
max_rounds = 3
target_similarity = 0.85
# base_url/model/api_key_env inherit [design] when empty
```

```bash
export GLM_API_KEY="…"        # or whatever api_key_env names
```

## Single figure

```bash
pixi run gaxis reconstruct pdf-<sha8>/fig-1 --engine podman
```

```
manifest: pdf-<sha8>/fig-1
method:   llm_reconstruction   model: glm-4.5v   rounds: 2
engine:   podman   level: L2
similarity: 0.781   history: [0.642, 0.781]
code:     data/assets/code/pdf-.../recon-<sha8>/figure.py
kb:       refreshed
```

Repair an existing author script (if the model leaves it unchanged, the result stays
`method = author_code`):

```bash
pixi run gaxis reconstruct pdf-<sha8>/fig-1 --repair --rounds 3
```

With data (the model is told to read `GAXIS_DATA` instead of inventing values):

```bash
pixi run gaxis reconstruct pdf-<sha8>/fig-1 --data my_table.csv
```

## What happens in one round

1. The model receives the reference image, the caption, the chart type and any visual-grammar
   notes, and must return one standalone matplotlib script (stdlib + matplotlib + numpy only).
2. The script is statically scanned, then run **offline in the sandbox** (no network, read-only
   root, resource limits).
3. The rendered raster is compared with the paper image with the same explainable metric used by
   `reproduce` (correlation, MAD, edges, ink, aspect ratio).
4. If similarity is below `target_similarity`, the model sees the rendered image, the similarity
   components and the traceback, and returns a corrected script.
5. The best round is kept: script copied to `data/assets/code/…`, manifest updated, KB page
   refreshed.

The `level` still comes from the thresholds in `[reproduction]`; it describes visual closeness.
`method` describes provenance. Both are stored, and retrieval sorts by level first, then
`author_code` before `llm_*`.

## Batch fallback

```bash
pixi run gaxis reproduce-paper pdf-<sha8> --reconstruct-missing
```

Figures that were `skipped` (no code), `needs_data`, `needs_env` or `failed` are reconstructed;
successful ones appear as `reconstructed` with their level. Author-code reproductions are never
replaced.

## Limits

- **Not for schematics, plates or micrographs**: a generated chart cannot honestly reproduce a
  diagram or a photo panel. gaxis still refuses those as data figures.
- **Approximate data**: without `--data`, the model reads values off the image, so the numbers are
  approximate. The manifest says `data_source: none`; do not present it as data-level reproduction.
- **Model quality matters**: rounds help, but a weak model plateaus. The similarity history tells
  you whether more rounds are worth it.
- **Cost/latency**: each round is one model call plus one sandbox run. Default is 3 rounds and early
  stop at 0.85.
- **No user data leaves the machine**: the model sees the public paper image and caption; the input
  table is mounted into the sandbox, not sent to the endpoint.

## Checkpoints

- [ ] `manifest.reproduction.method` is `llm_reconstruction` / `llm_repair` (not `author_code`);
- [ ] `similarity_history` has one entry per round and matches the attempts;
- [ ] the generated candidate has `generated: true` and a `code_sha256`;
- [ ] `kb_refresh` is not `failed`; retrieval shows the method.
