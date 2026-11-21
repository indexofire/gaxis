# Design quality: what gaxis actually selects for

> This document supersedes the earlier "quality calibration" approach. That attempt scored
> *technical* parameters (resolution, crop cleanliness, caption presence) and calibrated the score
> against a ranking of low-quality figures. The score was measuring "can we use the file", not
> "is this a good figure", and the corpus made any ranking arbitrary. Both mistakes are fixed here.

## 1. Two independent questions

| Question | Judged by | Stored as | Used for |
|---|---|---|---|
| **Can we use this asset at all?** | deterministic checks (caption, artwork, resolution, area, vector, crop cleanliness) | `chart_quality_score` (extraction) | a **gate**: do not reproduce or index unusable crops |
| **Is this a good figure?** | a vision model or a human, against a rubric | `design.method`, `design.aesthetic`, `design.visualization`, `design.score` | **selection and ranking** of what to reproduce |

They are never mixed. A technically perfect crop of an ugly chart is still a bad example; a
beautiful figure cut in half is still unusable.

## 2. What "good" means (the rubric)

Two axes, each 0–1:

**Aesthetic** — palette discipline (3–8 deliberate colours, colour-blind safe), whitespace and
margins, alignment and typographic consistency, no chart junk (heavy gridlines, 3-D, shadows,
decoration).

**Visualization** — the right chart for the data, axes labelled with units, uncertainty shown
(error bars / CI / box), legible at 89 mm print width (≥ 6 pt), sensible panel organisation.

## 3. Who judges

`[design] judge = "vision" | "heuristic"` (`src/gaxis/design_judge.py`):

- **vision** — an OpenAI-compatible vision model scores the rubric and returns JSON plus a short
  rationale; stored as `method: vision:<model>` with the model's rationale. This is the only
  automated way to judge aesthetics, and it must be calibrated against human ranks before its
  numbers decide anything important.
- **heuristic** (default, offline) — the objective half only: legibility from PDF font sizes,
  caption-declared units / uncertainty / panels, colour-blind safety, chart-vs-photo, whitespace.
  It sets `aesthetic: null` and `score: null`. It is a *screen*, never a taste claim.

```toml
[design]
judge = "vision"
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
api_key_env = "OPENAI_API_KEY"
```

Without a key the ingest falls back to the objective judge and records
`vision judge unavailable: …` in the manifest notes. No silent pretence.

## 4. Calibration (the real one)

1. Build a **golden set**: 20–30 figures you consider excellent, from your target journals
   (Nature Microbiology, Cell Host & Microbe, ISME J, mBio, …), plus 5–10 deliberately bad ones
   (default-matplotlib look, rainbow palettes, 3-D pies, unlabeled axes, grid-heavy).
2. `gaxis quality sheet --min-design 0.5` → `sheet.md` + contact sheet.
3. Rank 1..N by "would I put this in my paper?" (aesthetics + visualization, *not* extraction).
4. `gaxis quality calibrate <sheet.md>` → Spearman against the current judge. For the vision judge,
   compare its scores with your ranks; adjust the prompt/rubric if ρ < 0.7.
5. Only then use `design.score` for ranking thresholds.

## 4b. Calibration result (binary gold set)

Ranking 22 excellent figures against each other proved unreasonable (they are all good), so the
golden set uses a binary label: 22 curated journal figures = positive, 8 generated counterexamples
= negative. GLM-4.5V scores them with **AUC 0.991** (good mean 0.62, bad mean 0.26). The cached
judgements are a regression test; policy thresholds: ≥0.60 select (0.70 = strict), 0.45–0.60
dense-but-valid, <0.45 reject. Details: `data/corpus/golden/report.md`, `docs/vision-judge.md`.

## 4c. How the score is used (wired)

- At ingest, every figure is judged (vision when configured, objective fallback) and assigned a
  `design.tier` from `[design] gold_score` / `dense_score` (defaults 0.60 / 0.45):
  `gold` ≥ 0.60, `dense` 0.45–0.60, `reject` < 0.45; `null` means aesthetics was not judged.
- `reject` assets are still written as extraction assets (manifests + images) but are **not indexed**
  in the knowledge base (`[knowledge] include_rejected_design = false`). Flip it only for debugging.
- KB pages carry `design_tier`, `design_score`, `design_model`, and retrieval ranks by
  (reproduction level, design score, text score).
- The golden set (22 good + 8 bad) is a regression baseline: `tests/test_golden_design.py` replays
  cached judgements offline and fails if separation collapses.
- A larger **tiered library** is built from the judged series (137 perceptual-unique figures):
  `data/corpus/library/{gold,dense,reject}/` with per-tier `index.csv` and contact sheets
  (`scripts/curate_corpus.py library`). Current split: **gold 85, dense 36, reject 16**. This is a
  candidate pool, not the golden set: promote a figure into the golden set only after human review
  (all 22 curated figures went through that step).

## 4d. Plates are not single figures (owner finding, 2026-11-20)

The curated corpus images are **montages of several complete figures** from each article. Judging a
montage as one figure is meaningless: density/legibility complaints apply to the plate, and the
owner's keep/drop labels confirm the score does not separate them (keep spans 0.35–0.80, the single
drop scored 0.50).

Implemented:

- `design.plate_like` detects ≥2 tall content blocks separated by gutters (or a 2×2 grid);
  20/24 boundary images and 15/22 of the former "golden good" set are plates.
- `apply_plate_policy` (config `[design] skip_plates = true`) marks plates `archetype: "plate"`,
  clears `score`/`tier`, and records “style reference only”. Plates are still usable as palette and
  layout references, but they never stand in for a single-figure score.
- The golden set was split: `data/corpus/golden/plates/` (15, style references) and
  `data/corpus/golden/single/` (7). Single-figure calibration is now its own set:
  `data/corpus/single-boundary/` (17 paper figures with GLM scores) and
  `data/corpus/single-figures/review/` (24 crops labelled by the owner: keep / borderline / drop).

## 4e. Negative result on the current paper corpus (2026-11-20)

Owner labelling of 17 single-figure crops from the current pipeline (SE02 pre-proof, PLOS ONE, a demo):
**keep 0, borderline 3, drop 14**. The judge had put six of them in `gold` (≥0.55) — precision 0 at
that tier. Conclusion: those figures are technically extractable but not paper-worthy; this corpus
cannot calibrate single-figure design.

Consequence for the product: the design judge is a **prioritisation aid, not a truth source**, until
it is calibrated on single figures from high-quality papers. `plates` stay style references
(`skip_plates`), and the current KB does not claim design quality.

To build the right corpus, plates are now split into single-figure candidates:

```bash
pixi run python scripts/split_plates.py --plates data/corpus/boundary data/corpus/golden/plates     --out data/corpus/single-figures --limit 60
```

65 candidates were produced; the judge scored them, and `data/corpus/single-figures/review/` holds
the 12 highest and 12 lowest for owner labelling (keep/drop). Labels there become the real
single-figure calibration set.

## 4f. Rubric v3.1 — category first (2026-11-20)

The first single-figure labelling round exposed a systematic bias: the judge rewarded
micrographs and illustrations and penalised dense-but-valid figures (AUC 0.516). The rubric now
**classifies before scoring**:

- `chart` / `mixed` — scored on palette discipline, labels+units, uncertainty, legibility, panel
  organisation; density is not punished when labels stay readable.
- `schematic` / `micrograph` — capped at 3/10: references, not reusable data figures.
- `plate` — scored as a montage (completeness, palette consistency, layout), not as a single panel.

Result on 24 owner-labelled cases: **AUC 0.937** with rubric v3.1 (v3: 0.929; before: 0.516), with
precision/recall 0.89/0.89 at 0.55 and 1.00/0.78 at 0.60. The remaining disagreements are two figures (one kept schematic-like
composite at 0.30, one dropped chart at 0.55) — recorded in
`data/corpus/single-figures/review/report.md` and pinned by `tests/test_single_figure_judge.py`.

`skip_plates` now defaults to **false**: plate detection is a curation diagnostic (used to decide
whether to split an external montage), not a scoring rule for figures extracted from PDFs.

## 4g. Two scores, on purpose: design vs usefulness

`design.score` answers "is it well made". `usefulness_score` answers "is it the kind of figure a
microbiologist would reuse". They are separate because a clean but trivial PLOS plot can be
well-made (design 0.85) and still not worth reproducing (usefulness 0.34), while a dense figure from
a strong venue may be less polished but far more valuable.

Usefulness components (`src/gaxis/usefulness.py`, weights in `[usefulness]`: journal 0.20,
statistics 0.25, verification 0.25, panels 0.20, caption 0.10):

| component | signal |
|---|---|
| `journal` | venue tier from the DOI prefix — **deliberately compressed** (Nature 1.00, ASM 0.92, Microbiology Society 0.88, PLOS 0.82, bioRxiv 0.72, unknown 0.85) so venue is a tie-breaker, not the driver |
| `statistics` | caption declares uncertainty, sample size, units |
| `verification` | reproduction level L1 1.0 / L2 0.7 / L3 0.3 / none 0.2 |
| `panels` | panel count from the caption (a–d → 4) |
| `caption` | caption completeness |

Retrieval ranks by `reproduction_level`, then a **weighted** score
`0.7 × design_score + 0.3 × usefulness_score` (weights in `[ranking]`, normalised), then text
score. Design leads on purpose: the product is about reproducing well-designed figures, and venue
or panel count must never outrank a clearly better figure.
Both scores are stored in the manifest and in the KB page frontmatter. Usefulness is deterministic
(no model call) and explainable; it can be recalibrated once more labelled data exists.

## 5. Current state (honest)

- Objective half implemented and tested (legibility, units, uncertainty, panels, colour-blind,
  chart-vs-photo, whitespace). It **does not** claim aesthetics; `score` stays `null` until judged.
- Vision judge implemented (OpenAI-compatible chat completions, tolerant JSON parsing, rationale
  stored). **Enabled on the owner's GLM-4.5V endpoint** (`[design]` recipe in
  `docs/vision-judge.md`): ~1.8 s/figure, AUC 0.937 on 24 owner-labelled single figures. The local
  `qwen2.5vl:7b` fallback is ~145 s/figure and is for offline batches only.
- Corpus: the earlier low-quality sample (pre-proof gels, tiny PLOS panels) is still in the KB and
  must not be used for design calibration. One Nature Communications paper (7 figures) was added
  and parses correctly, but the product needs the golden set above, chosen by *you*.
- Retrieval ranks by (reproduction level, design score, text score); with `design.score` null it
  falls back to the objective visualization value, then text — no fabricated aesthetics.

## 6. What was wrong before (kept as a warning)

- The score was six technical components with weights "calibrated" on 10 figures that were all
  already similar, so the fit could not exceed ρ = 0.62 and the weights could not move.
- `crop_clean` penalised a tinted gel photo that was in fact a good figure (rank 3/10 by hand) —
  a heuristic mistake found only because a human looked.
- Nothing in that score encoded palette quality, chart appropriateness, or typographic craft.
