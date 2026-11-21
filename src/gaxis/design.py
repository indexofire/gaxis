"""Design quality: is this figure worth reproducing?

The extraction score answers "can we use this asset?" (caption present, artwork
legible, crop clean). It says nothing about whether the figure is *good*. This module
scores what the product actually cares about, in two independent halves:

    aesthetic       visual craft: palette discipline, whitespace, alignment,
                    minimalism (no chart junk), typography consistency
    visualization   information design: chart-like (not a photo dump), labels and
                    units, uncertainty shown, colour-blind safety, legible type at
                    print size, panel organisation

Both are computed from the image plus the caption text and the PDF's font sizes, so
every sub-score can be explained by a feature. `design_v1` is a rubric, not a learned
model: when human ranking disagrees, the feature table says which rule is wrong.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from .models.paper import DesignFeatures, DesignQuality

MAX_SIDE = 800
CVD_SAFE_DISTANCE = 0.22

_PANEL_RE = re.compile(
    r"(?:panels?\s+[a-h](?:\s*[-\u2013]\s*[a-h])?|\([a-h]\)|fig(?:ure)?\.?\s*\d+[a-h]\b)",
    re.IGNORECASE,
)
_UNIT_TOKENS = (
    "mm",
    "cm",
    "µm",
    "um",
    "nm",
    "ml",
    "mL",
    "µl",
    "μl",
    "µg",
    "mg",
    "kg",
    "g/L",
    "ng",
    "pg",
    "kb",
    "bp",
    "kbp",
    "mb",
    "gb",
    "cfu",
    "pfu",
    "rpm",
    "od600",
    "od",
    "°c",
    "°f",
    "h",
    "min",
    "s",
    "ms",
    "days",
    "dpi",
    "mol",
    "mm",
    "nm",
    "%",
    "‰",
    "log10",
    "log2",
    "fc",
    "fpkm",
    "tpm",
    "rpkm",
    "ph",
    "μs",
    "µm",
)
_UNCERTAINTY = (
    "error bar",
    "error bars",
    "standard deviation",
    "s.d.",
    "sd",
    "sem",
    "95% ci",
    "confidence interval",
    "confidence intervals",
    "interquartile",
    "i.q.r",
    "box plot",
    "boxplot",
    "shaded area",
    "shading",
    "±",
)


# ----------------------------------------------------------------- image side
def _load(source: bytes | Path) -> tuple[Any, Any]:
    import numpy as np
    from PIL import Image

    image = Image.open(io.BytesIO(source)) if isinstance(source, bytes) else Image.open(source)
    with image:
        rgb = image.convert("RGB")
        scale = MAX_SIDE / max(rgb.size)
        if scale < 1:
            rgb = rgb.resize((max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale))))
        colour = np.asarray(rgb, dtype="float32") / 255.0
    return colour, colour.mean(axis=2)


def _palette(colour: Any) -> tuple[tuple[str, ...], int, int, float]:
    """Dominant colours over non-background pixels, merged across anti-aliasing."""
    import numpy as np

    flat_pixels = colour.reshape(-1, 3)
    mask = flat_pixels.min(axis=1) < 0.88
    if mask.sum() < 50:
        return (), 0, 0, 0.0
    pixels = flat_pixels[mask]
    quantised = (pixels * 7).round().astype("int16")
    keys, inverse, counts = np.unique(quantised, axis=0, return_inverse=True, return_counts=True)
    sums = np.zeros((len(keys), 3), dtype="float64")
    np.add.at(sums, inverse, pixels)
    means = sums / counts[:, None]
    share = counts / counts.sum()
    entropy = float(-(share * np.log2(share + 1e-12)).sum())

    order = np.argsort(share)[::-1]
    merged: list[list[float]] = []
    for index in order:
        if share[index] < 0.001:
            continue
        rgb = means[index]
        if float(rgb.min()) > 0.88:
            continue
        for existing in merged:
            if float(np.linalg.norm(rgb - np.array(existing))) < 0.18:
                break
        else:
            merged.append([float(channel) for channel in rgb])
        if len(merged) >= 10:
            break
    palette = [
        f"#{int(rgb[0] * 255):02x}{int(rgb[1] * 255):02x}{int(rgb[2] * 255):02x}" for rgb in merged
    ]
    # neutrals (black text, grey axes, anti-aliasing) are not a palette choice
    chromatic = [rgb for rgb in merged if max(rgb) - min(rgb) > 0.12]
    return tuple(palette), len(chromatic), len(keys), entropy


# Machado et al. 2009, severity 1.0, linear RGB
_SIMULATIONS = {
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
}
CVD_MIN_CHROMA = 15.0


def _hue(rgb: tuple[float, float, float]) -> float:
    import colorsys

    return colorsys.rgb_to_hsv(*rgb)[0] * 360.0


def _is_rainbow(merged: list[list[float]]) -> bool:
    """A jet-style ramp: many saturated colours spanning most of the hue circle."""
    chromatic = [rgb for rgb in merged if max(rgb) - min(rgb) > 0.12]
    if len(chromatic) < 6:
        return False
    hues = sorted(_hue((rgb[0], rgb[1], rgb[2])) for rgb in chromatic)
    gaps = [hues[i + 1] - hues[i] for i in range(len(hues) - 1)]
    gaps.append(hues[0] + 360.0 - hues[-1])
    coverage = 360.0 - max(gaps)
    return coverage >= 150.0


def _hex_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _linear_to_lab(linear: list[float] | tuple[float, ...]) -> tuple[float, float, float]:
    x = linear[0] * 0.4124 + linear[1] * 0.3576 + linear[2] * 0.1805
    y = linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
    z = linear[0] * 0.0193 + linear[1] * 0.1192 + linear[2] * 0.9505
    x, y, z = x / 0.95047, y / 1.0, z / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _rgb_to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    return _linear_to_lab([_to_linear(channel) for channel in rgb])


def _simulate(
    rgb: tuple[float, float, float], matrix: tuple[tuple[float, ...], ...]
) -> tuple[float, ...]:
    linear = [_to_linear(channel) for channel in rgb]
    return tuple(sum(row[i] * linear[i] for i in range(3)) for row in matrix)


def _distinct_chromatic(palette: tuple[str, ...]) -> list[tuple[float, float, float]]:
    """Merge anti-aliasing variants so one colour does not compete with its own edge."""
    import numpy as np

    kept: list[tuple[float, float, float]] = []
    for hex_value in palette:
        rgb = _hex_rgb(hex_value)
        if max(rgb) - min(rgb) <= 0.12:
            continue
        if any(float(np.linalg.norm(np.array(rgb) - np.array(other))) < 0.12 for other in kept):
            continue
        kept.append(rgb)
    return kept


def _colorblind_safe(palette: tuple[str, ...]) -> bool | None:
    chromatic = _distinct_chromatic(palette)
    if len(chromatic) < 2:
        return None
    worst = 1e9
    for matrix in _SIMULATIONS.values():
        labs = [_linear_to_lab(_simulate(c, matrix)) for c in chromatic]
        for i in range(len(labs)):
            for j in range(i + 1, len(labs)):
                # hue/chroma distance: lightness differences do not help a CVD reader
                # separate two colours, so they must not rescue an unsafe palette
                distance = ((labs[i][1] - labs[j][1]) ** 2 + (labs[i][2] - labs[j][2]) ** 2) ** 0.5
                worst = min(worst, distance)
    return worst >= CVD_MIN_CHROMA


def _unused_gridline_density(gray: Any) -> float:
    import numpy as np

    ink = gray < 0.9
    width, height = ink.shape[1], ink.shape[0]
    row_share = ink.mean(axis=1)
    col_share = ink.mean(axis=0)
    # a gridline: a row/column mostly inked but sparse, spanning most of the figure
    rows = np.count_nonzero((row_share > 0.25) & (row_share < 0.85)) / max(height, 1)
    cols = np.count_nonzero((col_share > 0.25) & (col_share < 0.85)) / max(width, 1)
    return float(min(1.0, (rows + cols) * 6))  # ~6+ full-span lines reads as a grid


def _unused_alignment(gray: Any) -> float:
    import numpy as np

    ink = gray < 0.9
    row_profile = ink.mean(axis=1)
    col_profile = ink.mean(axis=0)

    # a well-built chart has a few dominant vertical/horizontal structures
    def peakiness(profile: Any) -> float:
        profile = profile - profile.mean()
        energy = float((profile**2).sum()) or 1.0
        top = np.sort(np.abs(profile))[-max(3, len(profile) // 40) :]
        return float((top**2).sum() / energy)

    return max(0.0, min(1.0, 0.5 * peakiness(row_profile) + 0.5 * peakiness(col_profile)))


def _margin_balance(gray: Any) -> float:
    import numpy as np

    ink = gray < 0.9
    height, width = ink.shape
    band = max(2, int(0.04 * min(height, width)))
    sides = [
        float(ink[:band, :].mean()),
        float(ink[-band:, :].mean()),
        float(ink[:, :band].mean()),
        float(ink[:, -band:].mean()),
    ]
    spread = float(np.std(sides))
    return max(0.0, 1.0 - min(1.0, spread * 4))


# ---------------------------------------------------------------- text side
def _caption_signals(caption: str, label_font_pt: float | None) -> dict[str, Any]:
    lowered = caption.lower()
    signals: list[str] = []
    has_units = any(
        re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", lowered) for token in _UNIT_TOKENS
    )
    has_uncertainty = any(marker in lowered for marker in _UNCERTAINTY)
    has_panels = bool(_PANEL_RE.search(caption))
    if has_uncertainty:
        signals.append("uncertainty")
    if has_units:
        signals.append("units")
    if has_panels:
        signals.append("panels")
    if "colour-blind" in lowered or "color-blind" in lowered or "colorblind" in lowered:
        signals.append("colourblind")
    if "log" in lowered:
        signals.append("log_scale")
    if "scale bar" in lowered:
        signals.append("scale_bar")
    if re.search(r"\bn\s*=\s*\d+", lowered):
        signals.append("sample_size")
    if "no grid" in lowered or "without grid" in lowered:
        signals.append("no_grid")
    return {
        "signals": tuple(signals),
        "has_units": has_units,
        "has_panels": has_panels,
        "has_uncertainty": has_uncertainty,
        "min_font_pt": label_font_pt,
    }


def _plate_from_gray(gray: Any) -> bool:
    """Count substantial content blocks separated by real gutters.

    A single figure has thin title/label bands around one plot body; a plate has two
    or more tall blocks (each ≥18 % of the content height) separated by gutters.
    """
    import numpy as np

    ink = gray < 0.9
    height, width = ink.shape
    if height < 200 or width < 200:
        return False
    rows = np.flatnonzero(ink.any(axis=1))
    cols = np.flatnonzero(ink.any(axis=0))
    if len(rows) < 20 or len(cols) < 20:
        return False
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    content_height = bottom - top
    content_ink = ink[top:bottom, :]

    row_profile = content_ink.mean(axis=1)
    gutter_min = max(6, int(content_height * 0.05))
    blocks: list[tuple[int, int]] = []
    start = 0
    for index, value in enumerate(row_profile):
        if value < 0.002:
            if index - start >= gutter_min:
                blocks.append((start, index))
            start = index
    blocks.append((start, len(row_profile)))
    substantial = [
        (begin, finish)
        for begin, finish in blocks
        if (finish - begin) >= 0.18 * content_height and content_ink[begin:finish, :].mean() > 0.004
    ]
    if len(substantial) >= 2:
        return True

    col_profile = content_ink.mean(axis=0)
    col_gutter = max(6, int((cols[-1] - cols[0]) * 0.05))
    col_blocks: list[tuple[int, int]] = []
    start = 0
    for index, value in enumerate(col_profile):
        if value < 0.002:
            if index - start >= col_gutter:
                col_blocks.append((start, index))
            start = index
    col_blocks.append((start, len(col_profile)))
    tall_columns = [
        (begin, finish)
        for begin, finish in col_blocks
        if (finish - begin) >= 0.35 * width and content_ink[:, begin:finish].mean() > 0.004
    ]
    return len(tall_columns) >= 2 and len(substantial) >= 2


def plate_like(source: bytes | Path) -> bool:
    """True when the image is a montage of several complete figures.

    Detect full-width/full-height blank gutters that split the content into ≥3
    substantial blocks. A multi-panel figure also has gutters, but its panels share
    axes and a legend; a plate stacks whole figures with their own captions/titles.
    The distinction is reported, never guessed silently: plates are style references,
    not single-figure calibration units.
    """
    _, gray = _load(source)
    return _plate_from_gray(gray)


def plate_blocks(source: bytes | Path) -> list[tuple[int, int, int, int]]:
    """Cut a plate into single-figure candidate boxes (row bands, then column gutters).

    Returns pixel boxes (left, top, right, bottom) in the original image. Boxes smaller
    than 3 % of the plate area are dropped: they are legends, scale bars or captions.
    """
    import io

    import numpy as np
    from PIL import Image

    opened = Image.open(io.BytesIO(source)) if isinstance(source, bytes) else Image.open(source)
    gray_image = opened.convert("L")
    width, height = gray_image.size
    gray = np.asarray(gray_image, dtype="float32") / 255.0
    ink = gray < 0.9

    def gutters(profile: Any, length: int, min_share: float = 0.012) -> list[tuple[int, int]]:
        edges: list[tuple[int, int]] = []
        start = None
        for index, value in enumerate(profile):
            blank = value < 0.002
            if blank and start is None:
                start = index
            elif not blank and start is not None:
                if index - start >= max(3, int(length * min_share)):
                    edges.append((start, index))
                start = None
        if start is not None and len(profile) - start >= max(3, int(length * min_share)):
            edges.append((start, len(profile)))
        return edges

    def segments(length: int, gaps: list[tuple[int, int]]) -> list[tuple[int, int]]:
        result = []
        cursor = 0
        for begin, finish in gaps:
            if begin > cursor:
                result.append((cursor, begin))
            cursor = finish
        if cursor < length:
            result.append((cursor, length))
        return result

    row_segments = segments(height, gutters(ink.mean(axis=1), height))
    boxes: list[tuple[int, int, int, int]] = []
    for top, bottom in row_segments:
        band = ink[top:bottom, :]
        if band.size == 0 or band.mean() < 0.004:
            continue
        for left, right in segments(width, gutters(band.mean(axis=0), width)):
            cell = ink[top:bottom, left:right]
            if cell.size == 0 or cell.mean() < 0.004:
                continue
            if (right - left) < 120 or (bottom - top) < 80:
                continue
            boxes.append((left, top, right, bottom))
    total = width * height
    return [box for box in boxes if (box[2] - box[0]) * (box[3] - box[1]) >= 0.03 * total]


def split_plate(
    source: bytes | Path,
    out_dir: Path,
    *,
    stem: str = "fig",
    max_blocks: int = 6,
) -> list[Path]:
    """Write single-figure crops cut from a plate; returns the written paths."""
    import io

    from PIL import Image

    opener = Image.open(io.BytesIO(source)) if isinstance(source, bytes) else Image.open(source)
    with opener as handle:
        rgb = handle.convert("RGB")
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for index, (left, top, right, bottom) in enumerate(
            plate_blocks(source)[:max_blocks], start=1
        ):
            candidate = rgb.crop((max(0, left - 2), max(0, top - 2), right + 2, bottom + 2))
            target = out_dir / f"{stem}-{index:02d}.png"
            candidate.save(target)
            written.append(target)
    return written


def apply_plate_policy(quality: DesignQuality, *, skip_plates: bool = True) -> DesignQuality:
    """Mark plates as style references: no single-figure score or tier."""
    if not quality.features.plate_like:
        return quality
    quality.archetype = "plate"
    if skip_plates:
        quality.aesthetic = None
        quality.score = None
        quality.tier = None
        quality.notes = [
            "multi-figure plate: several complete figures in one image; "
            "style reference only, not a single-figure score",
            *quality.notes,
        ]
    return quality


# ------------------------------------------------------- candidate sheets
def _font_label(report: DesignQuality) -> str:
    if report.features.min_font_pt is None:
        return "unknown"
    return f"{report.features.min_font_pt:.1f} pt"


def _csv_bool(value: bool | None) -> str:
    return "null" if value is None else str(int(value))


def build_candidate_sheet(
    images: list[Path], *, out_dir: Path, limit: int = 40
) -> tuple[Path, Path, Path]:
    """Numbered contact sheet + CSV of objective diagnostics for external figures.

    Used to curate a golden set from an article or a folder of exemplars. The numbers
    are for *your* selection; objective columns are diagnostics, never an aesthetic
    verdict.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    import logging

    from PIL import Image, UnidentifiedImageError

    logger = logging.getLogger(__name__)
    readable: list[Path] = []
    for image in images:
        try:
            with Image.open(image) as handle:
                handle.verify()
            readable.append(image)
        except (UnidentifiedImageError, OSError) as exc:
            logger.warning("skipping unreadable candidate %s: %s", image, exc)
    selected = readable[:limit]
    header = "| # | file | px | chart-like | colours | font hint |"
    rows = ["# Candidate figures", "", header, "|---|---|---|---|---|---|"]
    reports: list[tuple[int, Path, DesignQuality]] = []
    for index, image in enumerate(selected, start=1):
        from PIL import Image

        label = image.name
        with Image.open(image) as handle:
            width, height = handle.size
            if handle.format and handle.format.upper() not in {"PNG"}:
                converted = out_dir / f"candidate-{index:02d}.png"
                handle.convert("RGB").save(converted)
                image = converted
        report = analyse_design(image)
        reports.append((index, image, report))
        rows.append(
            f"| {index} | {label} | {width}x{height} | "
            f"{'yes' if report.features.chart_like else 'no'} | "
            f"{report.features.n_colours} | "
            f"{_font_label(report)} |"
        )
    sheet = out_dir / "candidates.md"
    sheet.write_text("\n".join(rows) + "\n", encoding="utf-8")
    csv = out_dir / "candidates.csv"
    csv.write_text(
        "n,file,pixels,chart_like,photo_like,n_colours,colorblind_safe,"
        "visualization_objective,selected(1/0)\n"
        + "\n".join(
            f"{index},{image.name},{image.stat().st_size},"
            f"{int(report.features.chart_like)},{int(report.features.photo_like)},"
            f"{report.features.n_colours},{_csv_bool(report.features.colorblind_safe)},"
            f"{report.visualization:.3f},"
            for index, image, report in reports
        )
        + "\n",
        encoding="utf-8",
    )
    columns = 5
    grid_rows = (len(reports) + columns - 1) // columns
    figure, axes = plt.subplots(
        grid_rows, columns, figsize=(3 * columns, 3.2 * grid_rows), squeeze=False
    )
    for position, (index, image, _) in enumerate(reports):
        axis = axes[position // columns][position % columns]
        axis.imshow(mpimg.imread(image))
        axis.set_title(f"#{index}", fontsize=10)
        axis.set_xticks([])
        axis.set_yticks([])
    for position in range(len(reports), grid_rows * columns):
        axes[position // columns][position % columns].axis("off")
    figure.tight_layout()
    contact = out_dir / "contact-sheet.png"
    figure.savefig(contact, dpi=110)
    plt.close(figure)
    return sheet, csv, contact


def dhash(path: Path, *, size: int = 8) -> int:
    """Difference hash: a cheap perceptual fingerprint for near-duplicate figures.

    The same figure re-uploaded with different compression produces the same dHash
    (up to a few bits), which byte hashing cannot catch.
    """
    import numpy as np
    from PIL import Image

    with Image.open(path) as handle:
        gray = handle.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
        pixels = np.asarray(gray, dtype="int16")
    bits = (pixels[:, 1:] > pixels[:, :-1]).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def hamming(left: int, right: int) -> int:
    return int((left ^ right).bit_count())


def dedupe_perceptual(paths: list[Path], *, max_distance: int = 6) -> list[Path]:
    """Keep the first of each near-duplicate cluster, preserving order."""
    kept: list[Path] = []
    fingerprints: list[int] = []
    for path in paths:
        try:
            fingerprint = dhash(path)
        except Exception as exc:  # noqa: BLE001 - unreadable files are skipped elsewhere
            import logging

            logging.getLogger(__name__).warning("dhash failed for %s: %s", path, exc)
            continue
        if any(hamming(fingerprint, other) <= max_distance for other in fingerprints):
            continue
        fingerprints.append(fingerprint)
        kept.append(path)
    return kept


def judge_directory(
    images: list[Path],
    *,
    judge: Any,
    out_dir: Path,
    captions: dict[str, str] | None = None,
    workers: int = 4,
    timeout_s: float = 120.0,
) -> tuple[Path, Path]:
    """Batch-judge a folder concurrently; one slow figure must not stall the batch."""
    import concurrent.futures
    import hashlib
    import json
    import sys
    import time as _time

    out_dir.mkdir(parents=True, exist_ok=True)
    captions = captions or {}

    seen: dict[str, str] = {}
    unique: list[Path] = []
    for image in images:
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen[digest] = str(image)
        unique.append(image)

    def _run(image: Path) -> dict[str, Any]:
        try:
            quality = judge.judge(image, caption=captions.get(image.name, ""))
            return {"file": str(image), **json.loads(quality.model_dump_json())}
        except Exception as exc:  # noqa: BLE001 - isolation per image is the point
            return {"file": str(image), "error": f"{type(exc).__name__}: {exc}"}

    records: list[dict[str, Any]] = []
    started = _time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_run, image) for image in unique]
        for position, future in enumerate(
            concurrent.futures.as_completed(futures, timeout=None), 1
        ):
            try:
                records.append(future.result(timeout=timeout_s))
            except Exception as exc:  # noqa: BLE001
                records.append({"file": "unknown", "error": f"timeout: {exc}"})
            if position % 20 == 0 or position == len(unique):
                elapsed = _time.perf_counter() - started
                print(
                    f"[judge] {position}/{len(unique)}  {elapsed / position:.1f}s/image",
                    file=sys.stderr,
                    flush=True,
                )

    (out_dir / "judgements.json").write_text(
        json.dumps({"judge": getattr(judge, "name", "unknown"), "records": records}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    ranked = sorted(
        [record for record in records if "error" not in record],
        key=lambda record: record.get("score") or 0.0,
        reverse=True,
    )
    csv = out_dir / "judgements.csv"
    csv.write_text(
        "rank,file,aesthetic,visualization,score,method\n"
        + "\n".join(
            f"{index},{record['file']},"
            f"{record['aesthetic'] if record['aesthetic'] is not None else ''},"
            f"{record['visualization']},{record['score'] if record['score'] is not None else ''},"
            f"{record['method']}"
            for index, record in enumerate(ranked, start=1)
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"[judge] done: {len(ranked)} scored, {len(records) - len(ranked)} failed",
        file=sys.stderr,
    )
    return out_dir / "judgements.json", csv


# ---------------------------------------------------------------- rubric
def analyse_design(
    source: bytes | Path,
    *,
    caption: str = "",
    label_font_pt: float | None = None,
) -> DesignQuality:
    colour, gray = _load(source)
    palette, n_colours, n_bins, entropy = _palette(colour)
    rainbow = _is_rainbow([list(_hex_rgb(c)) for c in palette])
    photo_like = n_bins > 150 and entropy > 4.0
    ink_ratio = float((gray < 0.9).mean())
    whitespace_ratio = float((gray > 0.95).mean())
    margins = _margin_balance(gray)
    safe = _colorblind_safe(palette)
    text = _caption_signals(caption, label_font_pt)
    chart_like = (not photo_like) and 0.01 <= ink_ratio <= 0.85
    plate = _plate_from_gray(gray)

    # objective signals only; aesthetics is judged by a vision model or a human
    legibility = (
        1.0
        if label_font_pt is None
        else (1.0 if label_font_pt >= 5 else 0.5 if label_font_pt >= 4 else 0.0)
    )
    legibility = (
        1.0
        if label_font_pt is None
        else (1.0 if label_font_pt >= 5 else 0.5 if label_font_pt >= 4 else 0.0)
    )
    visualization = max(
        0.0,
        min(
            1.0,
            0.25 * (1.0 if chart_like else 0.0)
            + 0.20 * legibility
            + 0.20 * (1.0 if text["has_units"] else 0.0)
            + 0.15 * (1.0 if text["has_uncertainty"] else 0.0)
            + 0.15 * (1.0 if safe else 0.5 if safe is None else 0.0)
            + 0.05 * (1.0 if text["has_panels"] else 0.0),
        ),
    )
    notes: list[str] = []
    if photo_like:
        notes.append("looks photographic: no chart grammar to reuse")
    if rainbow:
        notes.append("rainbow palette: no deliberate colour choices")
    if safe is False:
        notes.append("palette is not colour-blind safe")
    if label_font_pt is not None and label_font_pt < 5:
        notes.append(f"labels at {label_font_pt:.1f} pt: below the 5 pt print minimum")
    if not text["has_units"]:
        notes.append("caption does not state units")
    if not text["has_uncertainty"]:
        notes.append("no uncertainty representation mentioned")

    features = DesignFeatures(
        chart_like=chart_like,
        photo_like=photo_like,
        plate_like=plate,
        palette=list(palette),
        n_colours=n_colours,
        colorblind_safe=safe,
        ink_ratio=ink_ratio,
        whitespace_ratio=whitespace_ratio,
        margin_balance=margins,
        min_font_pt=label_font_pt,
        caption_signals=list(text["signals"]),
        has_units=bool(text["has_units"]),
        has_panels=bool(text["has_panels"]),
        has_uncertainty=bool(text["has_uncertainty"]),
    )
    return DesignQuality(
        model="objective_v1",
        method="objective",
        aesthetic=None,
        visualization=round(visualization, 4),
        score=None,
        features=features,
        notes=notes,
    )
