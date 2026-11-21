# Extraction-quality calibration (the gate, not the judgement)

> **Scope:** this document is about the *extraction gate* — can the file be used at all. It is not
> a measure of whether the figure is good; aesthetics and information design are judged separately
> in `docs/design-quality.md`. The earlier attempt to calibrate this score as "quality" was
> invalid and is documented there as a warning.

The extraction score decides whether an asset may be reproduced or indexed. It must be
explainable, so it is components with weights in `[quality]`, not a formula hidden in code.

| Component | 1.0 when | Why it matters |
|---|---|---|
| `caption` | caption longer than 20 characters | without a caption the asset is an image, not knowledge |
| `artwork` | a figure image exists | caption-only assets are still indexed but cannot be reproduced |
| `resolution` | largest side ≥ 900 px | legible at print size |
| `area` | crop covers 5–95 % of the page | rejects full-page scans and stray logos |
| `vector` | source artwork was vector | vector renders cleanly at any size |
| `cited` | body text refers to the figure | findable as an example, and semantically anchored |
| `crop_clean` | pixel check says the crop is a figure | catches body-text crops, blank areas, tinted scans and figures cut off at the frame |

`crop_clean` signals (all on a 600-px reduction, `src/gaxis/quality_image.py`):

- blank crop (almost no ink) → 0;
- body text: ≥6 horizontal ink bands with near-equal heights (CV < 0.2) separated by blank rows,
  plus mostly short horizontal strokes → 0.35;
- ink-heavy outer frame (figure clipped) → −0.25;
- large light-but-saturated background (tinted scan) → −0.2.

Thin-stroke figures (phylogenetic trees, line charts, scatter plots) look text-like by run length
alone, which is why the band test is required — it was added after a tree was misclassified as text.

Implementation: `src/gaxis/quality.py` + `quality_image.py`; defaults in `[quality]`; every manifest
stores the score in `geometry.crop_clean`. Manifests extracted before the component existed can be
updated with `pixi run gaxis quality backfill` (recomputes and re-ingests).

## Procedure (20–30 figures is enough)

```bash
pixi run gaxis quality sheet                # sheet.md + contact-sheet.png + rankings.template.csv
# rank 1..N in sheet.md by "how usable is this extraction", then:
cat > rankings.csv <<'CSV'
manifest_id,human_rank
pdf-958cda27/fig-1,1
pdf-958cda27/fig-3,2
CSV
pixi run gaxis quality calibrate rankings.csv        # or pass sheet.md directly
pixi run gaxis quality calibrate data/calibration/sheet.md --json
```

Regenerating a sheet that already contains ranks is refused (`sheet_has_ranks`); use
`gaxis quality sheet --force` only when you intend to throw the ranking away.

What to judge (the rubric is in the sheet header):

1. caption complete and self-describing?
2. artwork legible at print size — is the crop the figure and not body text?
3. is the whole figure present (not a fragment or a single panel)?
4. does the body text cite it?

Do **not** rank by how interesting the paper is; the score is about extraction fidelity.

## What the calibration reports

- `baseline` — Spearman ρ between the current score and your ranking.
- `best` — ρ after coordinate descent over the six weights (multiplicative and additive moves, so a
  zeroed component can be revived).
- `component_spearman` — which components actually correlate with your judgement; a negative value
  is a bug report against the extractor, not just a weight problem.
- a ready-to-paste `[quality]` block.

Acceptance from the plan: **ρ ≥ 0.7** (Spearman) between score order and human order. Below that,
either the weights or the extractor are wrong; report which component disagrees first.

## Status

`gaxis quality sheet` was generated from the current corpus (10 figures, SE02 + PLOS + demo) into
`data/calibration/` with the `crop` column. Calibration is **pending human ranking** — fill
`rankings.template.csv` (or the sheet's last column) and run `gaxis quality calibrate`.

Status note: the current corpus is homogeneous (every figure scores 0.73–0.87 because they all have
captions, artwork, resolution and citations). A meaningful calibration needs the failure modes too:
caption-only assets from pre-proofs, body-text crops, low-res scans, clipped figures. Those are all
representable (`crop_clean` = 0.35, `artwork` = 0, `resolution` = 0), so ingesting 10–20 more
diverse papers is the next step for calibration, not a change to the formula.
