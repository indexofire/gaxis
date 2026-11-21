---
type: analysis
asset_id: smoke-0001
paper_doi: 10.1099/mgen.0.000001
chart_type: line
reproduction_level: L1
preset_hint: nature_microbiology
image_path: assets/smoke-0001/figure.png
code_path: assets/smoke-0001/figure.py
---

# Rarefaction curve of 16S rRNA gene amplicons

Caption: Rarefaction curves of observed ASVs against sequencing depth for soil
samples under three nitrogen treatments; shaded bands are 95% confidence
intervals over five replicates.

Visual grammar: line chart; x = sequencing depth (reads), y = observed ASVs,
hue = nitrogen treatment; Okabe-Ito palette; no grid; legend outside right;
7 pt sans (Arial-metric) at 89 mm single-column width.

Code: matplotlib errorbar with caps and "o" markers, mean ± SD across replicates,
PDF + PNG at 600 dpi. The script is self-contained and runs without gaxis.

Image: `assets/smoke-0001/figure.png` — open the file directly; the brain only
stores its path, the multimodal host renders it.
