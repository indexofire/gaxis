"""Extraction-quality scoring and its calibration against human ranking.

The score decides which assets are worth reproducing and how they rank in retrieval,
so it must be explainable and tunable, not a pile of magic numbers. Components:

    caption      a real caption was extracted (not a fragment)
    artwork      the figure image exists at all
    resolution   rendered/extracted at a usable pixel size
    area         the crop occupies a plausible share of the page
    vector       the source was vector artwork
    cited        the body text refers to the figure

Weights live in ``[quality]`` and ``gaxis quality calibrate`` adjusts them from a
human ranking (Spearman against the score). Only 20-30 hand-ranked figures are needed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models.paper import ChartReproManifest, DesignQuality

COMPONENTS = ("caption", "artwork", "resolution", "area", "vector", "cited", "crop_clean")


@dataclass(frozen=True)
class QualityWeights:
    caption: float = 0.28
    artwork: float = 0.18
    resolution: float = 0.14
    area: float = 0.09
    vector: float = 0.13
    cited: float = 0.08
    crop_clean: float = 0.10

    def as_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in COMPONENTS}

    def normalised(self) -> QualityWeights:
        total = sum(self.as_dict().values()) or 1.0
        return QualityWeights(**{name: value / total for name, value in self.as_dict().items()})


def _caption_component(caption: str) -> float:
    return 1.0 if len(caption) > 20 else 0.33 if caption else 0.0


def _resolution_component(largest: int) -> float:
    if largest >= 900:
        return 1.0
    return 0.5 if largest >= 600 else 0.0


def _area_component(ratio: float) -> float:
    return 1.0 if 0.05 <= ratio <= 0.95 else 0.0


def components_from_figure(
    *,
    caption: str,
    has_artwork: bool,
    largest_pixels: int,
    area_ratio: float,
    is_vector: bool,
    cited: bool,
    crop_clean: float | None,
) -> dict[str, float]:
    return {
        "caption": _caption_component(caption),
        "artwork": 1.0 if has_artwork else 0.0,
        "resolution": _resolution_component(largest_pixels),
        "area": _area_component(area_ratio),
        "vector": 1.0 if is_vector else 0.0,
        "cited": 1.0 if cited else 0.0,
        # unknown crop quality is treated as "not verified", not as "good"
        "crop_clean": 0.0 if crop_clean is None else max(0.0, min(1.0, crop_clean)),
    }


def components_from_manifest(
    manifest: ChartReproManifest, *, data_root: Path | None = None
) -> dict[str, float]:
    geometry = manifest.geometry
    largest = (
        max(geometry.pixel_width or 0, geometry.pixel_height or 0) if geometry is not None else 0
    )
    crop_clean = geometry.crop_clean if geometry is not None else None
    if crop_clean is None and data_root is not None and manifest.chart_file:
        image = data_root / manifest.chart_file
        if image.is_file():
            from .quality_image import crop_clean_score

            crop_clean = crop_clean_score(image)
    return components_from_figure(
        caption=manifest.caption,
        has_artwork=geometry is not None,
        largest_pixels=largest,
        area_ratio=geometry.area_ratio if geometry is not None else 0.0,
        is_vector=bool(geometry and geometry.is_vector),
        cited=bool(manifest.citing_paragraph),
        crop_clean=crop_clean,
    )


def score_components(components: dict[str, float], weights: QualityWeights) -> float:
    total = sum(weights.as_dict().values()) or 1.0
    raw = sum(getattr(weights, name) * components.get(name, 0.0) for name in COMPONENTS)
    return round(max(0.0, min(1.0, raw / total)), 4)


def score_manifest(
    manifest: ChartReproManifest,
    weights: QualityWeights,
    *,
    data_root: Path | None = None,
) -> float:
    return score_components(components_from_manifest(manifest, data_root=data_root), weights)


def score_figure(
    *,
    caption: str,
    has_artwork: bool,
    largest_pixels: int,
    area_ratio: float,
    is_vector: bool,
    cited: bool,
    crop_clean: float | None,
    weights: QualityWeights,
) -> float:
    components = components_from_figure(
        caption=caption,
        has_artwork=has_artwork,
        largest_pixels=largest_pixels,
        area_ratio=area_ratio,
        is_vector=is_vector,
        cited=cited,
        crop_clean=crop_clean,
    )
    return score_components(components, weights)


def apply_category_policy(quality: DesignQuality, *, allow_nonchart: bool = False) -> DesignQuality:
    """Non-chart images are references, not reusable data figures (tier reject by default)."""
    if allow_nonchart:
        return quality
    if quality.category in {"schematic", "micrograph"}:
        quality.tier = "reject"
        quality.notes = [
            f"{quality.category}: not a data figure (reference only); "
            "set [design] allow_nonchart = true to keep it as an example",
            *quality.notes,
        ]
    return quality


def design_tier(score: float | None, *, gold: float = 0.55, dense: float = 0.45) -> str | None:
    """Policy bucket for a design score (None when aesthetics has not been judged)."""
    if score is None:
        return None
    if score >= gold:
        return "gold"
    if score >= dense:
        return "dense"
    return "reject"


# --------------------------------------------------------------- calibration
def _average_ranks(values: list[float]) -> list[float]:
    import numpy as np

    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype="float64")
    sorted_values = [values[index] for index in order]
    position = 0
    while position < len(values):
        end = position
        while end + 1 < len(values) and sorted_values[end + 1] == sorted_values[position]:
            end += 1
        average = (position + end) / 2.0 + 1.0
        for index in order[position : end + 1]:
            ranks[index] = average
        position = end + 1
    return ranks.tolist()


def spearman(left: Iterable[float], right: Iterable[float]) -> float:
    """Rank correlation without scipy; ties get average ranks."""
    import numpy as np

    x = list(left)
    y = list(right)
    if len(x) != len(y) or len(x) < 3:
        return 0.0
    rx = np.array(_average_ranks(x))
    ry = np.array(_average_ranks(y))
    rx -= rx.mean()
    ry -= ry.mean()
    denominator = float(np.sqrt((rx**2).sum() * (ry**2).sum()))
    return 0.0 if denominator == 0 else float((rx * ry).sum() / denominator)


@dataclass(frozen=True)
class CalibrationRow:
    manifest_id: str
    components: dict[str, float]
    human_rank: int  # 1 = best


@dataclass(frozen=True)
class CalibrationReport:
    samples: int
    baseline_weights: QualityWeights
    baseline_spearman: float
    best_weights: QualityWeights
    best_spearman: float
    component_spearman: dict[str, float]
    varying_components: tuple[str, ...] = ()
    distinct_scores: int = 0
    ceiling_spearman: float = 0.0

    @property
    def improved(self) -> bool:
        return self.best_spearman > self.baseline_spearman + 1e-9

    def as_dict(self) -> dict[str, Any]:
        return {
            "samples": self.samples,
            "baseline": {
                "weights": self.baseline_weights.as_dict(),
                "spearman": round(self.baseline_spearman, 4),
            },
            "best": {
                "weights": {
                    key: round(value, 4) for key, value in self.best_weights.as_dict().items()
                },
                "spearman": round(self.best_spearman, 4),
            },
            "component_spearman": {
                key: round(value, 4) for key, value in self.component_spearman.items()
            },
            "varying_components": list(self.varying_components),
            "distinct_scores": self.distinct_scores,
            "ceiling_spearman": round(self.ceiling_spearman, 4),
            "improved": self.improved,
        }

    def toml_snippet(self) -> str:
        lines = ["[quality]"]
        for name, value in self.best_weights.as_dict().items():
            lines.append(f"{name} = {value:.2f}")
        return "\n".join(lines)


def calibrate(
    rows: list[CalibrationRow],
    *,
    baseline: QualityWeights | None = None,
    passes: int = 4,
) -> CalibrationReport:
    """Coordinate-descent search for weights that match the human ranking better."""
    if len(rows) < 5:
        raise ValueError("calibration needs at least 5 ranked figures")
    weights = (baseline or QualityWeights()).normalised()
    human = [row.human_rank for row in rows]
    # rank 1 is best: correlate score against the negated rank
    target = [-rank for rank in human]

    def objective(candidate: QualityWeights) -> float:
        scores = [score_components(row.components, candidate) for row in rows]
        return spearman(scores, target)

    best_score = objective(weights)
    factors = (0.5, 0.75, 1.25, 1.5, 2.0)
    offsets = (0.05, 0.1, 0.2, 0.3)
    for _ in range(passes):
        improved = False
        for name in COMPONENTS:
            current = getattr(weights, name)
            # both multiplicative and additive moves, so a zeroed component can be revived
            candidates = [current * factor for factor in factors] + [
                current + delta for delta in offsets
            ]
            for value in candidates:
                trial_values = weights.as_dict()
                trial_values[name] = max(0.0, value)
                trial = QualityWeights(**trial_values).normalised()
                score = objective(trial)
                if score > best_score + 1e-6:
                    weights, best_score = trial, score
                    improved = True
                    break
        if not improved:
            break

    component_spearman = {
        name: spearman([row.components.get(name, 0.0) for row in rows], target)
        for name in COMPONENTS
    }
    varying = tuple(
        name
        for name in COMPONENTS
        if len({round(row.components.get(name, 0.0), 3) for row in rows}) > 1
    )
    scores = [score_components(row.components, weights) for row in rows]
    distinct_scores = len({round(score, 4) for score in scores})
    # Ceiling given the tiers the varying components already impose: no reweighting can
    # order samples inside a tie, so this is the best a linear score can do on this sample.
    tiers: dict[float, list[int]] = {}
    for index, score in enumerate(scores):
        tiers.setdefault(round(score, 4), []).append(index)
    ideal = [0.0] * len(rows)
    # ascending tiers; inside a tier the best human rank gets the largest value
    for tier_rank, (_, members) in enumerate(sorted(tiers.items()), start=1):
        ordered = sorted(members, key=lambda index: -rows[index].human_rank)
        for position, index in enumerate(ordered):
            ideal[index] = tier_rank * 1000 + position
    ceiling = spearman(ideal, target)
    baseline_weights = (baseline or QualityWeights()).normalised()
    baseline_scores = [score_components(row.components, baseline_weights) for row in rows]
    return CalibrationReport(
        samples=len(rows),
        baseline_weights=baseline_weights,
        baseline_spearman=spearman(baseline_scores, target),
        best_weights=weights,
        best_spearman=best_score,
        component_spearman=component_spearman,
        varying_components=varying,
        distinct_scores=distinct_scores,
        ceiling_spearman=ceiling,
    )


# ------------------------------------------------------------------- sheet
SHEET_HEADER = """\
# Design-quality sheet

Rank these figures by **how good the figure is** — a figure you would be happy to
reproduce in your own paper, best first (1 = best). Two things matter:

**Aesthetics** — palette discipline (3-8 deliberate colours), whitespace and margins,
alignment, no chart junk (heavy gridlines, 3D, shadows), consistent typography.

**Visualization** — the right chart for the data, complete axis labels and units,
uncertainty shown (error bars / CI / box), colour-blind-safe palette, legible type at
print size (≥6 pt), sensible panel organisation.

`extract` and `crop` are mechanical checks (can the asset be used at all). Do not rank
on those; they are a gate, not a judgement.

Write your ranks into `rankings.csv` (`manifest_id,human_rank`) and run
`pixi run gaxis quality calibrate rankings.csv`.
"""


def _sheet_has_ranks(path: Path) -> bool:
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 8 and cells[0].isdigit() and cells[-1]:
            return True
    return False


def build_sheet(
    manifests: list[ChartReproManifest],
    *,
    data_root: Path,
    out_dir: Path,
    limit: int = 30,
    weights: QualityWeights | None = None,
    force: bool = False,
    sort_by: str = "design",
    min_design: float = 0.0,
) -> tuple[Path, Path | None]:
    """Write sheet.md (+ contact-sheet.png) and return their paths.

    Refuses to overwrite a sheet that already contains human ranks: losing someone's
    judgement to a regeneration is unacceptable.
    """
    weights = weights or QualityWeights()
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = out_dir / "sheet.md"
    if not force and _sheet_has_ranks(sheet_path):
        raise FileExistsError(
            f"{sheet_path} already contains human ranks; pass force=True to overwrite"
        )
    pool = [
        manifest
        for manifest in manifests
        if (
            (
                manifest.design.score
                if manifest.design and manifest.design.score is not None
                else (manifest.design.visualization if manifest.design else 0.0)
            )
            >= min_design
        )
    ]
    if sort_by == "extraction":
        selected = sorted(
            pool,
            key=lambda item: score_manifest(item, weights, data_root=data_root),
            reverse=True,
        )[:limit]
    else:
        selected = sorted(
            pool,
            key=lambda item: (
                (
                    item.design.score
                    if item.design and item.design.score is not None
                    else (item.design.visualization if item.design else 0.0)
                ),
                score_manifest(item, weights, data_root=data_root),
            ),
            reverse=True,
        )[:limit]
    out_dir.mkdir(parents=True, exist_ok=True)
    header = "| # | figure | caption | px | crop | extract | aes | vis | design | human rank |"
    rows: list[str] = [SHEET_HEADER, "", header, "|---|---|---|---|---|---|---|---|---|---|"]
    thumbs: list[tuple[int, Path]] = []
    for index, manifest in enumerate(selected, start=1):
        geometry = manifest.geometry
        pixels = f"{geometry.pixel_width}x{geometry.pixel_height}" if geometry is not None else "-"
        caption = (manifest.caption or "").replace("|", "\\|")[:100]
        rows.append(
            f"| {index} | {manifest.figure_ref} ({manifest.manifest_id}) | "
            f"{caption} | "
            f"{pixels} | {_crop_label(manifest, data_root)} | "
            f"{score_manifest(manifest, weights, data_root=data_root):.2f} | "
            f"{_aesthetic_label(manifest)} | "
            f"{(manifest.design.visualization if manifest.design else 0.0):.2f} | "
            f"{_design_label(manifest)} | |"
        )
        if manifest.chart_file:
            image = data_root / manifest.chart_file
            if image.is_file():
                thumbs.append((index, image))
    sheet = out_dir / "sheet.md"
    sheet.write_text("\n".join(rows) + "\n", encoding="utf-8")
    template = out_dir / "rankings.template.csv"
    lines = ["manifest_id,human_rank"]
    lines.extend(f"{manifest.manifest_id}," for manifest in selected)
    template.write_text("\n".join(lines) + "\n", encoding="utf-8")
    contact = _contact_sheet(thumbs, out_dir / "contact-sheet.png")
    return sheet, contact


def parse_sheet_ranks(markdown: str) -> list[tuple[str, int]]:
    """Read ``manifest_id, human_rank`` pairs from a filled-in sheet.md."""
    ranks: list[tuple[str, int]] = []
    for line in markdown.splitlines():
        if not line.startswith("| ") or not line.rstrip().endswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].isdigit():
            continue
        raw_rank = cells[-1]
        if not raw_rank or not raw_rank.isdigit():
            continue
        figure_cell = cells[1]
        match = None
        for token in figure_cell.replace("(", " ").replace(")", " ").split():
            if "/fig-" in token:
                match = token
        if match is None:
            continue
        ranks.append((match, int(raw_rank)))
    return ranks


def _design_label(manifest: ChartReproManifest) -> str:
    if manifest.design is None or manifest.design.score is None:
        return "-"
    return f"{manifest.design.score:.2f}"


def _aesthetic_label(manifest: ChartReproManifest) -> str:
    if manifest.design is None or manifest.design.aesthetic is None:
        return "-"
    return f"{manifest.design.aesthetic:.2f}"


def _crop_label(manifest: ChartReproManifest, data_root: Path) -> str:
    geometry = manifest.geometry
    value = geometry.crop_clean if geometry is not None else None
    if value is None and manifest.chart_file:
        image = data_root / manifest.chart_file
        if image.is_file():
            from .quality_image import crop_clean_score

            value = crop_clean_score(image)
    return "-" if value is None else f"{value:.2f}"


def _contact_sheet(thumbs: list[tuple[int, Path]], path: Path) -> Path | None:
    if not thumbs:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    columns = 5
    rows = (len(thumbs) + columns - 1) // columns
    figure, axes = plt.subplots(rows, columns, figsize=(3 * columns, 3 * rows), squeeze=False)
    for position, (index, image) in enumerate(thumbs):
        axis = axes[position // columns][position % columns]
        axis.imshow(mpimg.imread(image))
        axis.set_title(f"#{index}", fontsize=9)
        axis.set_xticks([])
        axis.set_yticks([])
    for position in range(len(thumbs), rows * columns):
        axes[position // columns][position % columns].axis("off")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=120)
    plt.close(figure)
    return path
