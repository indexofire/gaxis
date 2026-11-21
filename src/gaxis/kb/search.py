"""Retrieval over the paper knowledge base (module F, first route: text + metadata).

gbrain returns chunk hits, not assets; this module collapses them to one hit per
page, reads the page's frontmatter, applies the filters gbrain cannot express
(level ordering, preset post-filter) and ranks by (reproduction level, score).
"""

from __future__ import annotations

from pathlib import Path

from ..models.spec import ChartType
from ..models.tools import ChartAssetSummary
from .base import KbError, KnowledgeBase

LEVEL_RANK = {"L1": 3, "L2": 2, "L3": 1, "none": 0}


def _rank(level: str | None) -> int:
    return LEVEL_RANK.get((level or "none").upper(), 0)


def _chart_type(value: object) -> ChartType | None:
    if not value:
        return None
    try:
        return ChartType(str(value))
    except ValueError:
        return None


def _combined(design: float | None, usefulness: float | None) -> float:
    """Weighted design/usefulness score; an unjudged design is treated as neutral."""
    from ..config import settings

    ranking = settings().config.ranking
    total = ranking.design_weight + ranking.usefulness_weight or 1.0
    design_value = 0.5 if design is None else design
    use_value = 0.5 if usefulness is None else usefulness
    return (ranking.design_weight * design_value + ranking.usefulness_weight * use_value) / total


def search_assets(
    kb: KnowledgeBase,
    query: str,
    *,
    k: int = 5,
    chart_type: str | None = None,
    min_level: str | None = None,
    preset: str | None = None,
    design_tier: str | None = None,
    has_code: bool | None = None,
    dedupe: bool = False,
    types: list[str] | None = None,
    data_root: Path | None = None,
    query_image: Path | None = None,
    fetch_limit: int = 8,
) -> list[ChartAssetSummary]:
    where: dict[str, str] = {}
    if chart_type:
        where["chart_type"] = chart_type
    hits = kb.search(
        query,
        limit=max(fetch_limit, k * 2),
        types=types or ["analysis"],
        where=where or None,
    )
    query_hash: int | None = None
    if query_image is not None:
        from ..design import dhash

        try:
            query_hash = dhash(query_image)
        except Exception as exc:  # an unreadable query degrades to text
            raise KbError(f"cannot read query image {query_image}: {exc}") from exc
    image_cache: dict[Path, int | None] = {}

    best: dict[str, float] = {}
    for hit in hits:
        best[hit.slug] = max(best.get(hit.slug, 0.0), hit.score)

    ranked: list[tuple[int, float, float, float, ChartAssetSummary]] = []
    for slug, score in sorted(best.items(), key=lambda item: item[1], reverse=True)[:fetch_limit]:
        page = kb.get_page(slug)
        if page is None:
            continue
        front = page.get("frontmatter") or {}
        level = str(front.get("reproduction_level") or "none").upper()
        if min_level and _rank(level) < _rank(min_level):
            continue
        preset_hint = front.get("preset_hint")
        if preset and str(preset_hint or "") != preset:
            continue
        raw_tier = front.get("design_tier")
        tier = str(raw_tier) if raw_tier in {"gold", "dense", "reject"} else None
        if design_tier and tier != design_tier:
            continue
        code_path = front.get("code_path")
        has_recorded_code = bool(code_path)
        if has_code is not None and has_recorded_code != has_code:
            continue
        image_path = front.get("image_path")
        thumb: str | None = None
        if image_path and data_root is not None:
            candidate = data_root / str(image_path)
            thumb = str(candidate) if candidate.is_file() else None
        image_similarity = None
        if query_hash is not None and thumb is not None:
            image_similarity = _image_similarity(query_hash, Path(thumb), image_cache)
        similarity = front.get("visual_similarity")
        design_score = front.get("design_score")
        usefulness = front.get("usefulness_score")
        summary = ChartAssetSummary(
            asset_id=str(front.get("asset_id") or slug),
            paper_title=str(front["paper_title"]) if front.get("paper_title") else None,
            doi=str(front["doi"]) if front.get("doi") else None,
            chart_type=_chart_type(front.get("chart_type")),
            reproduction_level=level if level in {"L1", "L2", "L3"} else None,  # type: ignore[arg-type]
            visual_similarity=float(similarity) if isinstance(similarity, (int, float)) else None,
            preset_hint=str(preset_hint) if preset_hint else None,
            thumb_path=thumb,
            design_score=(float(design_score) if isinstance(design_score, (int, float)) else None),
            design_tier=tier,  # type: ignore[arg-type]
            usefulness_score=(float(usefulness) if isinstance(usefulness, (int, float)) else None),
            image_similarity=image_similarity,
            has_code=has_recorded_code,
        )
        design_rank = float(design_score) if isinstance(design_score, (int, float)) else None
        use_rank = float(usefulness) if isinstance(usefulness, (int, float)) else None
        image_rank = -1.0 if image_similarity is None else image_similarity
        ranked.append((_rank(level), _combined(design_rank, use_rank), score, image_rank, summary))

    if query_hash is not None:
        # the image is the query: similarity leads, evidence and design break ties
        ranked.sort(key=lambda item: (item[3], item[0], item[1], item[2]), reverse=True)
    else:
        # level first, then the weighted design/usefulness score; text breaks ties
        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    assets = [item[4] for item in ranked]
    if dedupe:
        assets = _dedupe_by_fingerprint(assets, image_cache)
    return assets[:k]


def _image_similarity(query_hash: int, path: Path, cache: dict[Path, int | None]) -> float | None:
    """dHash similarity in [0, 1]; None when the candidate image is unreadable."""
    from ..design import dhash, hamming

    if path not in cache:
        try:
            cache[path] = dhash(path)
        except Exception:  # noqa: BLE001 - missing thumbnails simply do not rank
            cache[path] = None
    candidate = cache[path]
    if candidate is None:
        return None
    return 1.0 - hamming(query_hash, candidate) / 64.0


def _dedupe_by_fingerprint(
    assets: list[ChartAssetSummary], cache: dict[Path, int | None]
) -> list[ChartAssetSummary]:
    """Collapse perceptually identical figures (same dHash), keeping the higher rank."""
    from ..design import dhash

    seen: set[int] = set()
    kept: list[ChartAssetSummary] = []
    for asset in assets:
        if not asset.thumb_path:
            kept.append(asset)
            continue
        path = Path(asset.thumb_path)
        if path not in cache:
            try:
                cache[path] = dhash(path)
            except Exception:  # noqa: BLE001 - an unreadable thumbnail cannot be deduped
                cache[path] = None
        fingerprint = cache[path]
        if fingerprint is None or fingerprint in seen:
            if fingerprint is not None:
                continue
            kept.append(asset)
            continue
        seen.add(fingerprint)
        kept.append(asset)
    return kept
