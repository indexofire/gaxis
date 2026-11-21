# Journal presets and publication lint

Presets are data: `src/gaxis/style/journal_presets/*.toml`. Adding a journal must never require
touching `render/templates/*.tpl` (ADR-16).

## 1. Available presets (microbiology first)

| Preset | Single column | Double column | Base type | DPI | Target |
|---|---|---|---|---|---|
| `default` | 120 × 80 mm | 180 × 120 mm | 9 pt | 600 | unspecified journal, safe fallback |
| `nature` | 89 × 60 mm | 183 × 120 mm | 7 pt | 600 | Nature family |
| `nature_microbiology` | 89 × 60 mm | 183 × 120 mm | 7 pt | 600 | Nature Microbiology |
| `asm` | 84 × 62 mm | 175 × 120 mm | 8 pt | 600 | mBio, AEM, Microbiology Spectrum |
| `isme` | 90 × 65 mm | 180 × 125 mm | 7.5 pt | 600 | ISME Journal |
| `cell_host_microbe` | 85 × 60 mm | 174 × 110 mm | 7 pt | 600 | Cell Host & Microbe |
| `microbial_genomics` | 90 × 65 mm | 190 × 130 mm | 8 pt | 600 | Microbial Genomics (Microbiology Society) |

Check at runtime: `pixi run gaxis presets` / `--json`.

Single vs double: if `width_mm` exceeds the single-column width by >15%, the double-column height is
used automatically (`style/presets.py::resolve_size`). Override explicitly with `--width/--height`.

## 2. Fields

| Key | Meaning |
|---|---|
| `width_single_mm`, `width_double_mm` | column geometry, the numbers reviewers check |
| `height_mm`, `height_double_mm` | default heights per width class |
| `base_font_pt` | ticks, legend text, annotations |
| `label_font_pt` | axis labels |
| `title_font_pt` | title / panel captions |
| `line_width_pt`, `spine_width_pt`, `marker_size_pt` | stroke weights; journals have minimums around 0.25–0.5 pt |
| `dpi` | raster export DPI (vector output is unaffected) |
| `font_family` | ordered fallback chain, resolved against installed fonts |
| `palette` | default palette name; `okabe_ito` unless a journal prescribes otherwise |
| `legend_frame`, `grid` | chart-junk switches |
| `spines` | which spines remain (`["left","bottom"]` is the default minimal frame) |
| `vector_required` | when true, a raster-only render is a lint **error** |

Font policy: matplotlib resolves the chain via `font_manager`; ggplot2 passes the resolved family to
`theme_classic(base_family=...)`. On this workstation `Arial` resolves to `Liberation Sans`
(metric-compatible). A fallback is never silent: lint `L005` reports a font mismatch, and the
manifest records the resolved font under `style.font`.

## 3. Backend mapping

| Preset field | matplotlib (`style/rc.py`) | ggplot2 (`render/templates/r_header.tpl`) |
|---|---|---|
| `base_font_pt` | `font.size`, tick sizes, legend size | `theme_classic(base_size=)`, `axis.text`, `legend.text` |
| `label_font_pt` | `axes.labelsize` | `axis.title` |
| `title_font_pt` | `axes.titlesize` | `plot.title` |
| `spine_width_pt` | `axes.linewidth`, tick widths | `axis.line`, `axis.ticks` |
| `line_width_pt` | `lines.linewidth` | `geom_line(linewidth=)` |
| `marker_size_pt` | `lines.markersize` | `geom_point(size = pt * 0.3528)` (ggplot2 sizes are mm) |
| `spines`, `grid`, `legend_frame` | rcParams | `theme()` elements |
| width/height | `figure.figsize` in inches | `ggsave(units = "mm")` |
| vector safety | `pdf.fonttype = 42`, `svg.fonttype = "none"` | `cairo_pdf`, `svglite` |

Both backends write the same aggregation statistics (mean + SD, or the mean of a supplied `yerr`
column), so a figure switched from Python to R is comparable rather than merely similar.

## 4. Output safety

- `savefig.bbox="tight"`, `pad_inches=0.01` (matplotlib) and `ggsave` margins keep exported geometry
  within a few percent of the nominal width; lint `L006` tolerates 3% (info) and fails at 15%.
- PNG/TIFF are written at the preset DPI with an opaque white background.
- PDF fonts are embedded TrueType (Type 42) / cairo; Type 3 is a lint error.

## 5. Lint rules

| Code | Severity | Meaning | Typical fix |
|---|---|---|---|
| L001 | error | output file missing or empty | check `formats`, check `render.log` |
| L002 | error | no vector output while required | add `pdf` or `svg` |
| L003 | error / info | raster DPI < 300 (error) or < preset DPI (info) | raise `--dpi` |
| L004 | error | PDF contains Type 3 fonts | use `pdf.fonttype=42` / `cairo_pdf` |
| L005 | warning | font fallback vs preset | install the journal font, or accept Liberation Sans |
| L006 | error / info | geometry off by >15% / >3% | set `--width/--height`, avoid manual `bbox` changes |
| L007 | warning | palette not colour-blind safe | switch to `okabe_ito` / `viridis` |
| L008 | warning | title/axis label not found in SVG text layer | check labels, or export SVG (not just PDF) |
| L009 | warning | file smaller than 2 KB | likely a blank figure |

Run standalone on finished files (any tool, any language):

```bash
pixi run gaxis lint figure.pdf figure.svg --preset nature_microbiology
pixi run gaxis lint figure.png --preset asm --width 84 --height 62 --json
```

Exit code `3` when any error-level issue exists, so this can gate a submission CI.

## 6. Adding a journal preset

1. Create `src/gaxis/style/journal_presets/<name>.toml` with the fields above.
2. Run `pixi run gaxis presets` — no code change should be necessary.
3. Render once in both backends and confirm `lint: clean`:
   ```bash
   pixi run gaxis render --data examples/demo/expr.tsv --preset <name> --out data/check
   pixi run gaxis render --data examples/demo/expr.tsv --preset <name> --backend r --out data/check-r
   ```
4. Record the source of the numbers (author guidelines URL + access date) in the TOML
   `description` — reviewer-facing numbers without a citation will be doubted.

## 7. Palettes

| Name | Colour-blind safe | Notes |
|---|---|---|
| `okabe_ito` | yes | default; Nature-recommended for CVD accessibility |
| `viridis` | yes | perceptually uniform, print safe |
| `greys` | yes | mono print / photocopy |
| `npg` | no | Nature Publishing Group palette, high saturation |
| `set2` | no | ColorBrewer Set2 |

Non-CVD-safe palettes are allowed but flagged (`L007`), so the trade-off is explicit rather than
accidental.
