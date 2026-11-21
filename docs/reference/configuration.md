# Configuration Reference

The configuration is a TOML file plus a small set of environment variable overrides. **Bad configuration raises `config_invalid`; it never falls back silently.**

## Lookup order (first match wins)

1. `--config PATH`
2. `$GAXIS_CONFIG`
3. `./gaxis.toml` (project)
4. `${XDG_CONFIG_HOME:-~/.config}/gaxis/config.toml` (user)
5. Built-in defaults

```bash
cp gaxis.example.toml gaxis.toml
pixi run gaxis config          # show effective values (including overrides)
```

`data_root` defaults to `./data` and can be overridden with `GAXIS_DATA_DIR`.

## `[confirmation]` — When user confirmation is required

| Key | Default | Description |
|---|---|---|
| `mode` | `auto` | `auto` decides by confidence; `always` always confirms; `never` never asks |
| `min_confidence` | `0.6` | In `auto` mode, confirmation is required first below this value |

## `[render]`

| Key | Default | Description |
|---|---|---|
| `timeout_s` | `180` | Upper limit for a single render/script execution |
| `default_preset` | `default` | Preset used when the CLI does not specify one |
| `default_backend` | `python` | `python` or `r` |

## `[ingest]` — Paper acquisition

| Key | Default | Description |
|---|---|---|
| `default_mode` | `kb_first` | `kb_first` or `full` |
| `allow_network` | `true` | When disabled, only local files are processed |
| `timeout_s` | `900` | Upper limit for parsing a single paper |
| `min_quality` | `0.0` | Below this extraction quality, no manifest is created |
| `contact_email` | `""` | Polite-pool address for Unpaywall/NCBI (recommended) |
| `max_download_mb` | `40` | PDF size limit |
| `with_code` | `true` | Whether to try to locate code repositories |
| `repo_timeout_s` | `120` | Upper limit for cloning a single repository |
| `max_repos` | `2` | Maximum number of repositories cloned per paper |

## `[quality]` — Extraction quality weights

| Key | Default |
|---|---|
| `caption` | 0.28 |
| `artwork` | 0.18 |
| `resolution` | 0.14 |
| `area` | 0.09 |
| `vector` | 0.13 |
| `cited` | 0.08 |
| `crop_clean` | 0.10 |

Changing weights changes existing scores: re-run `quality backfill` and `kb ingest`.

## `[usefulness]` — Usefulness weights

| Key | Default |
|---|---|
| `journal` | 0.35 |
| `statistics` | 0.20 |
| `verification` | 0.20 |
| `panels` | 0.15 |
| `caption` | 0.10 |

## `[ranking]` — Retrieval fusion

| Key | Default | Description |
|---|---|---|
| `design_weight` | 0.70 | Weight of the design score |
| `usefulness_weight` | 0.30 | Weight of the usefulness score |

The design lead is intentional: a strong journal must not push a weak figure up.

## `[design]` — Design review

| Key | Default | Description |
|---|---|---|
| `judge` | `heuristic` | `heuristic` (offline objective features) or `vision` |
| `base_url` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `model` | `gpt-4o-mini` | Vision model name |
| `api_key_env` | `OPENAI_API_KEY` | Which environment variable to read the key from |
| `timeout_s` | `300` | Upper limit per image |
| `max_side` | `768` | Longest side of the image sent to the model (latency knob) |
| `gold_score` | `0.60` | Eligible for gold standard / prioritized retrieval |
| `dense_score` | `0.45` | Below this, judged as `reject` |
| `retries` | `2` | Retries on failure |
| `skip_plates` | `false` | External plate figures are not scored as single figures |
| `allow_nonchart` | `false` | Whether to ingest diagrams/micrographs as cases |

Example (the GLM vision model used locally):

```toml
[design]
judge = "vision"
base_url = "https://open.bigmodel.cn/api/coding/paas/v4"
model = "glm-4.5v"
api_key_env = "GLM_API_KEY"
max_side = 768
```

## `[reconstruct]` — LLM-assisted reconstruction

Fallback for figures without runnable author code: the model writes a script, the sandbox runs it
and compares the render with the paper image. Results are recorded as
`reproduction.method = llm_reconstruction` (or `llm_repair`) and never as an author reproduction.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | allow the batch fallback (`reproduce-paper --reconstruct-missing`) |
| `base_url` | `""` | OpenAI-compatible endpoint; empty inherits `[design]` |
| `model` | `""` | vision/code model; empty inherits `[design]` |
| `api_key_env` | `""` | key env var; empty inherits `[design]` |
| `max_rounds` | `3` | generate → render → compare → revise rounds |
| `target_similarity` | `0.85` | stop early at this similarity |
| `max_side` | `1024` | image long side sent to the model |
| `timeout_s` | `300` | per model request |
| `temperature` | `0.0` | deterministic generation |

## `[sandbox]` — Reproduction isolation

| Key | Default | Description |
|---|---|---|
| `backend` | `podman` | `podman` or `local` (development only) |
| `image` | `gaxis-repro:py312` | Base Python image |
| `autobuild` | `true` | Automatically build/pull the image when missing |
| `autobuild_packages` | `matplotlib==3.11.2`, `numpy==2.5.5` | Base plotting stack |
| `per_paper_env` | `true` | Build derived images from per-paper repository dependencies |
| `r_image` | `gaxis-repro-r:4.5` | R image |
| `r_base_image` | `docker.io/rocker/tidyverse:4.5` | Base R image |
| `r_packages` | `svglite`, `patchwork`, `cowplot` | Additional R packages |
| `network` | `false` | Containers have no network by default |
| `memory` | `4g` | Memory limit |
| `cpus` | `2.0` | CPU limit |
| `pids_limit` | `256` | Process count limit |
| `timeout_s` | `300` | Upper limit per run |
| `allow_network` | `false` | Whether the network may be explicitly opened up |

**Do not weaken isolation**: no network, read-only root, cap-drop, resource limits, and `no-new-privileges` are all defaults;
changing them requires explicit configuration keys and tests.

## `[reproduction]` — Tier thresholds

| Key | Default | Description |
|---|---|---|
| `l1_similarity` | 0.85 | Similarity threshold for L1 |
| `l2_similarity` | 0.55 | Similarity threshold for L2 |
| `compare_size` | 256 | Longest side images are scaled to before comparison |

Thresholds are defined only here; runners and tests must not hardcode them.

## `[knowledge]` — gbrain

| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | When disabled, retrieval returns `degraded` |
| `source` | `paper-kb` | gbrain source |
| `binary` | `null` | Path to the gbrain CLI (default PATH → `scripts/gbrain.sh`) |
| `gbrain_home` | `null` | Data directory (default `${XDG_DATA_HOME:-~/.local/share}/gaxis/gbrain`) |
| `types` | `["analysis"]` | Page types to retrieve |
| `timeout_s` | `120` | Upper limit per call |
| `retries` | `3` | Retries on failure |
| `auto_ingest` | `true` | Automatically ingest after parsing |
| `include_rejected_design` | `false` | Whether to index pages whose design was judged `reject` |

## Environment variable overrides

| Variable | Overrides |
|---|---|
| `GAXIS_DATA_DIR` | `data_root` |
| `GAXIS_CONFIG` | Configuration file path |
| `GAXIS_CONFIRM_MODE` | `[confirmation] mode` |
| `GAXIS_CONFIRM_MIN_CONFIDENCE` | `[confirmation] min_confidence` |
| `GAXIS_INGEST_MODE` | `[ingest] default_mode` |
| `GAXIS_RENDER_TIMEOUT` | `[render] timeout_s` |
| `GAXIS_CONTACT_EMAIL` | `[ingest] contact_email` |
| `GAXIS_SANDBOX_BACKEND` | `[sandbox] backend` |
| `GAXIS_SANDBOX_IMAGE` | `[sandbox] image` |
| `GAXIS_SANDBOX_TIMEOUT` | `[sandbox] timeout_s` |
| `GAXIS_KB_ENABLED` | `[knowledge] enabled` |
| `GAXIS_GBRAIN_BIN` | `[knowledge] binary` |
| `GAXIS_GBRAIN_HOME` | `[knowledge] gbrain_home` |
| `GAXIS_MCP_TOKEN` | Bearer token for the MCP server (required) |

## Data directory layout

```
data/
  renders/<figure_id>/        rendered outputs + figure.py/.R + manifest.json + render.log
  manifests/                  ChartReproManifest (paper figures; authoritative)
  assets/                     paper figures, code assets, template code
  repro/<asset>/<sha8>/       reproduction workdir + reproduction.json
  synthetic/                  synthetic input tables
  kb/state.json               page content hashes (idempotent ingest)
  kb/sheets/                  contact sheet
  kb/selections.jsonl         selection feedback
  ops/queue.db                queue
  ops/heartbeat.json          last run
```

`data/` is not committed to git; knowledge-base pages can be rebuilt from manifests.
