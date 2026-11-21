# Vision judge: candidates, cost, and how to calibrate

Aesthetics is not measurable from pixels with a formula (see `docs/design-quality.md`). The only
scalable judge is a vision-language model scoring the rubric, calibrated against your ranking. This
document lists candidates, their wiring, and the measured local baseline.

## 1. Wiring (all candidates except Claude)

The judge speaks **OpenAI-compatible chat completions** with an image data URL, so one
implementation covers almost everything:

```toml
[design]
judge = "vision"
base_url = "…"          # provider endpoint, /v1 style
model = "…"
api_key_env = "…"       # env var holding the key
max_side = 768          # vision input long side (smaller = faster on CPU)
timeout_s = 300
```

`gaxis design judge <image> --caption "…"` scores a single file; ingest/backfill applies it to
figures. `aesthetic`, `visualization` and the model's rationale are stored in the manifest
(`design.method = "vision:<model>"`); a failure falls back to the objective judge and says so.

## 2. Candidates

| Candidate | Access | Strengths | Rough cost / figure | Notes |
|---|---|---|---|---|
| **Qwen-VL-Max** (DashScope) | `https://dashscope.aliyuncs.com/compatible-mode/v1`, `DASHSCOPE_API_KEY` | best-in-class chart/OCR reading, strong Chinese | ~$0.002–0.01 | good default for figure-heavy judging |
| **GLM-4.5V / 4.6V** (Zhipu) | `https://open.bigmodel.cn/api/paas/v4`, `ZHIPUAI_API_KEY` | strong Chinese, cheap, already on a GLM plan in this stack | ~$0.001–0.005 | Chinese prompt/rubric works well |
| **GPT-4o-mini / GPT-4.1-mini** (OpenAI) | `https://api.openai.com/v1`, `OPENAI_API_KEY` | reliable JSON, follows the rubric strictly | ~$0.001–0.003 | safest for structured output |
| **Gemini 2.5 Flash** (Google, OpenAI-compat) | `https://generativelanguage.googleapis.com/v1beta/openai`, `GEMINI_API_KEY` | cheap, good visual reasoning | ~$0.0005–0.002 | strong price/quality for batch |
| **Claude Sonnet** (Anthropic) | Anthropic Messages API | best "designer's eye" in practice | ~$0.01–0.02 | needs a small adapter (not OpenAI-compatible) |
| **qwen2.5vl:7b** (local, Ollama) | `http://127.0.0.1:11434/v1`, no key | free, private, offline | 0 | **measured 145–150 s/figure on this CPU at 768 px**; weaker score separation |

Costs are per-figure estimates for one 1024-px-class image and a short JSON answer; check current
provider pricing before committing to a batch.

## 2b. Verified on this stack: GLM-4.5V via the GLM coding plan

The existing GLM coding key works for vision on **both** endpoints (the coding plan endpoint serves
`glm-4.5v`):

```toml
[design]
judge = "vision"
base_url = "https://open.bigmodel.cn/api/coding/paas/v4"
model = "glm-4.5v"
api_key_env = "GLM_API_KEY"
max_side = 1024
timeout_s = 120
```

Measured: ~1.8 s per figure (coding endpoint), 3.0 s (standard endpoint), JSON answers reliable.

Calibration (final, `data/corpus/golden/`): 22 curated journal figures from the WeChat
the "高分文章配色指南" (high-impact figure colour guide) series + 8 generated counterexamples.

| Metric | Value |
|---|---|
| good mean / range | **0.623** / 0.45–0.90 |
| bad mean / range | **0.256** / 0.15–0.45 |
| AUC | **0.991** |

The owner found the 22 curated figures "all high quality, hard to rank", so calibration uses a
**binary** judgement (gold vs counterexample) rather than a total order — a ranking that cannot be
produced reliably is worse than no ranking. The judge's rationales are specific and actionable
("gene names illegible at 89 mm", ">20 colours in panel B", "consistent colour-blind-safe palette").
The offline regression `tests/test_golden_design.py` replays the cached judgements and fails if the
separation degrades.

Policy used for this sample: ≥0.55 select; 0.45–0.55 dense-but-valid; <0.45 reject (highest bad
= 0.45). The shipped default is the stricter **0.60 / 0.45** (see §5).

Single-figure calibration with rubric v3.1 (category first): **AUC 0.937** on 24 owner-labelled
figures; 0.60 → precision/recall 0.80/0.89, 0.70 → 1.00/0.78. Details in
`data/corpus/single-figures/review/report.md`.

## 3. Measured local baseline (this machine)

Ollama `qwen2.5vl:7b` (6 GB), Intel Core Ultra 7 255H, no GPU:

| Input size | Latency | Result on a CNS multi-panel figure | Result on a gel composite |
|---|---|---|---|
| 1024 px | 367 s | aes 0.60 / vis 0.70 | — |
| 768 px | ~145 s | aes 0.60 / vis 0.70 | aes 0.50 / vis 0.30 |
| 448 px | ~148 s | — | aes 0.50 / vis 0.30 |

Observations: latency is dominated by prefill over image tokens (768 ≈ 448 because the model
re-tiles to its own resolution); the 7B's rationale is plausible ("palette not colour-blind safe",
"panel organisation could be clearer") but its absolute scores are compressed and it is not a
substitute for a frontier model during calibration.

## 4. Calibration protocol

1. Curate 20–30 figures you consider excellent plus 5–10 bad ones (the WeChat palette series is a
   good source: `gaxis design candidates <dir>`).
2. Rank them 1..N yourself (design only, not extraction).
3. Run the judge over the same set, compute Spearman against your ranking
   (`gaxis quality calibrate`, using the design score once it is judged).
4. Target ρ ≥ 0.7. If it misses, inspect the rationale for the biggest disagreements: usually the
   rubric needs one concrete rule (e.g. "shared legends across panels are good", "gradient
   backgrounds are decoration").
5. Only then use `design.score` for selection thresholds; record the model + prompt version in the
   manifest so old judgements are comparable.

## 4b. Wiring

Judging runs at `ingest_paper`/`quality backfill` time. The resulting score is bucketed by
`[design] gold_score` (0.60) and `dense_score` (0.45); `reject` figures stay out of the knowledge
base unless `[knowledge] include_rejected_design = true`. See `docs/design-quality.md` §4c.

## 5. Current status

- **GLM-4.5V is wired and used** on the owner's coding plan endpoint
  (`base_url = https://open.bigmodel.cn/api/coding/paas/v4`, `model = glm-4.5v`,
  `api_key_env = GLM_API_KEY`): ~1.8 s per figure at 768 px. This is the judge behind the current
  calibration.
- Calibration: binary gold set (22 curated vs 8 counterexamples) AUC **0.991**; single-figure set
  (24 owner labels: keep/borderline/drop) AUC **0.937** with rubric v3.1. Both are replayed as
  offline regression tests (`tests/data/*_judgements.json`).
- The local `qwen2.5vl:7b` (Ollama) remains a fallback for offline batches (~145 s/figure at
  768 px; 1024 px is ~6 min). It is not used for continuous judging.
- Policy thresholds: `gold_score = 0.60`, `dense_score = 0.45`; `0.70` behaves as a strict mode
  (precision 1.00 / recall 0.78 on the labelled set). The thresholds are configuration, never
  constants in code.
