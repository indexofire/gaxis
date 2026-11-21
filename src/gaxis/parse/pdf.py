"""PDF -> figures, captions, citing paragraphs (M1 vertical slice).

Uses PyMuPDF. Captions are detected **per text line**, not per text block: real
papers frequently put the caption in the same block as body text, so block-level
matching finds nothing. Raster figures come from image XObjects; vector figures are
rendered from the drawings' bounding box above their caption, because most journal
figures are vector and skipping them would lose the best assets.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..models.paper import FigureGeometry
from ..quality_image import crop_clean_score
from . import captions

_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)")


@dataclass(frozen=True)
class TextLine:
    bbox: tuple[float, float, float, float]
    text: str
    size: float


@dataclass(frozen=True)
class TextBlock:
    bbox: tuple[float, float, float, float]
    lines: tuple[TextLine, ...]
    index: int

    @property
    def text(self) -> str:
        return " ".join(line.text for line in self.lines)


@dataclass(frozen=True)
class ImageBlock:
    bbox: tuple[float, float, float, float]
    width: int
    height: int
    data: bytes
    ext: str


@dataclass
class ExtractedFigure:
    number: int
    figure_ref: str
    caption: str
    page: int
    image_bytes: bytes | None
    image_ext: str
    geometry: FigureGeometry | None
    artwork_missing: bool = False
    pairing_note: str = ""
    label_font_pt: float | None = None


@dataclass
class ParsedPaper:
    path: Path
    sha256: str
    title: str
    doi: str | None
    page_count: int
    figures: list[ExtractedFigure] = field(default_factory=list)
    citations: dict[int, list[str]] = field(default_factory=dict)
    full_text: str = ""


def _blocks(page: object) -> tuple[list[TextBlock], list[ImageBlock]]:
    text_blocks: list[TextBlock] = []
    image_blocks: list[ImageBlock] = []
    raw = page.get_text("dict")["blocks"]  # type: ignore[attr-defined]
    for index, block in enumerate(raw):
        bbox = tuple(round(float(v), 2) for v in block["bbox"])
        if block.get("type") == 1:
            data = block.get("image")
            if not data:
                continue
            image_blocks.append(
                ImageBlock(
                    bbox=bbox,  # type: ignore[arg-type]
                    width=int(block.get("width", 0)),
                    height=int(block.get("height", 0)),
                    data=bytes(data),
                    ext=str(block.get("ext", "png")),
                )
            )
            continue
        lines: list[TextLine] = []
        for line in block.get("lines") or []:
            spans = line.get("spans") or []
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            sizes = [float(span.get("size", 0)) for span in spans]
            line_bbox = tuple(round(float(v), 2) for v in line.get("bbox", bbox))
            lines.append(
                TextLine(
                    bbox=line_bbox,  # type: ignore[arg-type]
                    text=text,
                    size=round(max(sizes) if sizes else 0.0, 2),
                )
            )
        if lines:
            text_blocks.append(TextBlock(bbox=bbox, lines=tuple(lines), index=index))  # type: ignore[arg-type]
    return text_blocks, image_blocks


def _merge_caption(
    flat: list[tuple[int, int, TextLine]],
    position: int,
    used: set[int],
    page_width: float,
) -> tuple[str, tuple[float, float, float, float], float]:
    """Join the caption's lines: same font size, same column, no paragraph gap."""
    _, _, first = flat[position]
    size = first.size
    bbox = list(first.bbox)
    parts = [first.text]
    used.add(position)
    for cursor in range(position + 1, len(flat)):
        if cursor in used:
            break
        _, _, line = flat[cursor]
        if captions.is_caption_start(line.text):
            break
        overlap = min(bbox[2], line.bbox[2]) - max(bbox[0], line.bbox[0])
        if overlap < 8:
            # margin artefacts (line numbers, running heads) sit outside the column;
            # skip them instead of ending the caption early
            if (line.bbox[2] - line.bbox[0]) < 0.08 * page_width:
                continue
            break
        if abs(line.size - size) > 1.5:
            break
        gap = line.bbox[1] - bbox[3]
        if gap > max(8.0, 2.6 * size) or gap < -1.5 * size:
            break
        parts.append(line.text)
        bbox = [
            min(bbox[0], line.bbox[0]),
            min(bbox[1], line.bbox[1]),
            max(bbox[2], line.bbox[2]),
            max(bbox[3], line.bbox[3]),
        ]
        used.add(cursor)
    return captions.join_blocks(parts), (bbox[0], bbox[1], bbox[2], bbox[3]), size


def _paragraphs(flat: list[tuple[int, int, TextLine]], used: set[int]) -> list[str]:
    """Rebuild paragraphs from unused lines, keeping block boundaries."""
    grouped: dict[int, list[str]] = {}
    for position, (block_index, _, line) in enumerate(flat):
        if position in used:
            continue
        grouped.setdefault(block_index, []).append(line.text)
    return [captions.join_blocks(lines) for lines in grouped.values() if lines]


def _pick_image(
    caption_bbox: tuple[float, float, float, float],
    images: list[ImageBlock],
    taken: set[int],
    page_height: float,
) -> int | None:
    best: tuple[float, int] | None = None
    for position, image in enumerate(images):
        if position in taken:
            continue
        # the artwork must start above the caption; a slight overlap is normal when
        # the axes and caption share a baseline
        if image.bbox[1] >= caption_bbox[1] - 4:
            continue
        if (image.bbox[3] - image.bbox[1]) > 0.85 * page_height:
            continue
        overlap = min(caption_bbox[2], image.bbox[2]) - max(caption_bbox[0], image.bbox[0])
        if overlap <= 0:
            continue
        distance = abs(caption_bbox[1] - image.bbox[3])
        if best is None or distance < best[0]:
            best = (distance, position)
    return best[1] if best else None


def _vector_region(
    page: object,
    caption_bbox: tuple[float, float, float, float],
    long_lines: list[TextLine],
) -> tuple[float, float, float, float] | None:
    """Geometry of the artwork directly above a caption.

    Vector figures have text labels of their own (axis ticks), so "everything above
    the last text line" collapses to nothing and "all drawings above the caption"
    swallows body text. The reliable band is between the **last long text line**
    (body paragraph or previous caption) and the caption itself; figure-internal
    labels are short and therefore do not truncate it.
    """
    page_rect = page.rect  # type: ignore[attr-defined]
    page_height = float(page_rect.height)
    above = [line for line in long_lines if line.bbox[3] <= caption_bbox[1] - 2]
    top = max((line.bbox[3] for line in above), default=page_rect.y0 + 36) + 2.0
    bottom = caption_bbox[1] - 3.0
    x0 = max(page_rect.x0 + 20, caption_bbox[0] - 6)
    x1 = min(page_rect.x1 - 20, caption_bbox[2] + 6)
    band = (x0, top, x1, bottom)
    if (bottom - top) >= 40 and (bottom - top) <= 0.8 * page_height and _has_artwork(page, band):
        return band
    fallback = _drawings_cluster(page, caption_bbox)
    if fallback is not None:
        return fallback
    return None


def _luminance(color: tuple[float, ...]) -> float:
    red, green, blue = ([*list(color), 0.0, 0.0, 0.0])[:3]
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _visible_ink(item: dict) -> bool:
    """Ignore watermarks and page furniture: white/very light fills and strokes."""
    colors = [c for c in (item.get("fill"), item.get("color")) if c]
    if not colors:
        return False
    return min(_luminance(tuple(c)) for c in colors) < 0.7


def _has_artwork(page: object, rect: tuple[float, float, float, float]) -> bool:
    """True when the band actually contains vector drawing, not just white space.

    A caption with no figure in the PDF (pre-proofs, figure files delivered
    separately) must be recorded as caption-only, never as a crop of body text.
    """
    import pymupdf

    box = pymupdf.Rect(*rect)
    for item in page.get_drawings():  # type: ignore[attr-defined]
        drawing = item.get("rect")
        if drawing is None or not _visible_ink(item):
            continue
        if drawing.intersects(box) and drawing.get_area() > 4:
            return True
    return False


def _drawings_cluster(
    page: object, caption_bbox: tuple[float, float, float, float]
) -> tuple[float, float, float, float] | None:
    """Fallback: union of the drawing cluster immediately above the caption."""
    page_rect = page.rect  # type: ignore[attr-defined]
    page_area = float(page_rect.width * page_rect.height)
    eligible: list[tuple[float, float, float, float]] = []
    for item in page.get_drawings():  # type: ignore[attr-defined]
        rect = item.get("rect")
        if rect is None or not _visible_ink(item):
            continue
        box = (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
        if box[3] > caption_bbox[1] + 1:
            continue
        if box[1] < caption_bbox[1] - 0.85 * page_rect.height:
            continue
        if (box[2] - box[0]) * (box[3] - box[1]) > 0.9 * page_area:
            continue  # page background / frame
        eligible.append(box)
    if eligible:
        eligible.sort(key=lambda box: box[3], reverse=True)
        cluster = [eligible[0]]
        cluster_top = eligible[0][1]
        for box in eligible[1:]:
            if cluster_top - box[3] <= 25:  # touching/adjacent art belongs together
                cluster.append(box)
                cluster_top = min(cluster_top, box[1])
            else:
                break
        x0 = min(box[0] for box in cluster)
        y0 = min(box[1] for box in cluster)
        x1 = max(box[2] for box in cluster)
        y1 = max(box[3] for box in cluster)
        if x1 - x0 > 0.3 * page_rect.width and y1 - y0 > 30:
            return (x0 - 4, y0 - 4, x1 + 4, min(y1 + 4, caption_bbox[1] - 1))
    return None


def _render(
    page: object, rect: tuple[float, float, float, float], dpi: int
) -> tuple[bytes, int, int] | None:
    import pymupdf

    page_rect = page.rect  # type: ignore[attr-defined]
    clip = pymupdf.Rect(
        max(rect[0], page_rect.x0),
        max(rect[1], page_rect.y0),
        min(rect[2], page_rect.x1),
        min(rect[3], page_rect.y1),
    )
    if clip.width < 20 or clip.height < 20:
        return None
    pixmap = page.get_pixmap(clip=clip, dpi=dpi)  # type: ignore[attr-defined]
    return pixmap.tobytes("png"), pixmap.width, pixmap.height


def _title(doc: object, first_page_blocks: list[TextBlock]) -> str:
    metadata_title = (doc.metadata or {}).get("title") or ""  # type: ignore[attr-defined]
    if len(metadata_title.strip()) > 5 and "untitled" not in metadata_title.lower():
        return metadata_title.strip()
    candidates = [
        line
        for block in first_page_blocks
        for line in block.lines
        if line.size >= 10 and len(line.text) >= 8 and not captions.is_caption_start(line.text)
    ]
    if candidates:
        return captions.clean_text(max(candidates, key=lambda line: line.size).text)
    return ""


def parse_pdf(
    path: Path,
    *,
    render_dpi: int = 300,
    min_area_ratio: float = 0.015,
    min_pixels: int = 120,
) -> ParsedPaper:
    import pymupdf

    file = Path(path).expanduser()
    data = file.read_bytes()
    doc = pymupdf.open(stream=data, filetype="pdf")
    sha256 = hashlib.sha256(data).hexdigest()
    figures: list[ExtractedFigure] = []
    paragraphs: list[str] = []
    orphans: list[tuple[int, ImageBlock, float]] = []
    seen_numbers: set[int] = set()
    title = ""
    all_text: list[str] = []

    for page_index in range(doc.page_count):
        page_number = page_index + 1
        page = doc[page_index]
        text_blocks, image_blocks = _blocks(page)
        page_area = float(page.rect.width * page.rect.height)
        all_text.extend(block.text for block in text_blocks)
        if page_number == 1:
            title = _title(doc, text_blocks)

        flat = [
            (block.index, line_index, line)
            for block in text_blocks
            for line_index, line in enumerate(block.lines)
        ]
        used: set[int] = set()
        taken_images: set[int] = set()
        for position, (_, _, line) in enumerate(flat):
            if position in used:
                continue
            label = captions.parse_label(line.text)
            if label is None:
                continue
            number, _ = label
            if number in seen_numbers:
                used.add(position)
                continue
            caption, caption_bbox, _size = _merge_caption(
                flat, position, used, float(page.rect.width)
            )
            image_bytes: bytes | None = None
            image_ext = "png"
            geometry: FigureGeometry | None = None

            image_position = _pick_image(
                caption_bbox, image_blocks, taken_images, float(page.rect.height)
            )
            if image_position is not None:
                image = image_blocks[image_position]
                area_ratio = (
                    (image.bbox[2] - image.bbox[0]) * (image.bbox[3] - image.bbox[1]) / page_area
                )
                if (
                    area_ratio >= min_area_ratio
                    and image.width >= min_pixels
                    and image.height >= min_pixels
                ):
                    taken_images.add(image_position)
                    image_bytes, image_ext = image.data, image.ext
                    geometry = FigureGeometry(
                        page=page_number,
                        bbox=image.bbox,
                        pixel_width=image.width,
                        pixel_height=image.height,
                        is_vector=False,
                        area_ratio=round(area_ratio, 4),
                        source="image_xobject",
                        crop_clean=crop_clean_score(image_bytes),
                    )
            if geometry is None:
                long_lines = [
                    candidate
                    for _, _, candidate in flat
                    if len(candidate.text) > 40
                    or (candidate.bbox[2] - candidate.bbox[0]) > 0.5 * page.rect.width
                ]
                region = _vector_region(page, caption_bbox, long_lines)
                rendered = _render(page, region, render_dpi) if region is not None else None
                if rendered is not None and region is not None:
                    png, width, height = rendered
                    area_ratio = (region[2] - region[0]) * (region[3] - region[1]) / page_area
                    image_bytes, image_ext = png, "png"
                    geometry = FigureGeometry(
                        page=page_number,
                        bbox=region,
                        pixel_width=width,
                        pixel_height=height,
                        is_vector=True,
                        area_ratio=round(area_ratio, 4),
                        source="vector_region",
                        crop_clean=crop_clean_score(png),
                    )
            artwork_missing = geometry is None or image_bytes is None
            label_font_pt = None
            if geometry is not None:
                inside = [
                    line.size
                    for _, _, line in flat
                    if line.size > 0
                    and line.bbox[0] >= geometry.bbox[0] - 2
                    and line.bbox[2] <= geometry.bbox[2] + 2
                    and line.bbox[1] >= geometry.bbox[1] - 2
                    and line.bbox[3] <= geometry.bbox[3] + 2
                ]
                label_font_pt = round(min(inside), 2) if inside else None
            seen_numbers.add(number)
            figures.append(
                ExtractedFigure(
                    number=number,
                    figure_ref=captions.figure_ref(number),
                    caption=caption,
                    page=page_number,
                    image_bytes=image_bytes,
                    image_ext=image_ext,
                    geometry=geometry,
                    artwork_missing=artwork_missing,
                    label_font_pt=label_font_pt,
                )
            )
        captions_on_page = any(captions.is_caption_start(line.text) for _, _, line in flat)
        if not captions_on_page:
            for position, image in enumerate(image_blocks):
                if position in taken_images:
                    continue
                ratio = (
                    (image.bbox[2] - image.bbox[0]) * (image.bbox[3] - image.bbox[1]) / page_area
                )
                if ratio >= 0.05 and image.width >= 300 and image.height >= 300:
                    orphans.append((page_number, image, round(ratio, 4)))
        paragraphs.extend(_paragraphs(flat, used))

    # Pre-proof layouts put all artwork in a separate section: pair the leftovers in order.
    missing = [figure for figure in figures if figure.artwork_missing]
    for figure, (page_number, image, ratio) in zip(missing, orphans, strict=False):
        figure.image_bytes = image.data
        figure.image_ext = image.ext
        figure.artwork_missing = False
        figure.pairing_note = (
            "artwork paired across pages: "
            f"caption on page {figure.page}, image on page {page_number} (pre-proof layout)"
        )
        figure.geometry = FigureGeometry(
            page=page_number,
            bbox=image.bbox,
            pixel_width=image.width,
            pixel_height=image.height,
            is_vector=False,
            area_ratio=ratio,
            source="image_xobject",
            crop_clean=crop_clean_score(image.data),
        )

    citations: dict[int, list[str]] = {}
    for figure in figures:
        cited = captions.extract_citations(paragraphs, figure.number)
        if cited:
            citations[figure.number] = cited

    doi = None
    match = _DOI_RE.search(" ".join(all_text))
    if match:
        doi = match.group(1).rstrip(".,;)")[:120]
    return ParsedPaper(
        path=file,
        sha256=sha256,
        title=title or file.stem,
        doi=doi,
        page_count=doc.page_count,
        figures=sorted(figures, key=lambda figure: figure.number),
        citations=citations,
        full_text="\n".join(all_text)[:400_000],
    )
