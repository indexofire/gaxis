"""Visual comparison: how close is a reproduction to the original figure?

Deliberately dependency-light (PIL + numpy): a global structural score plus edge
and ink agreement, penalised by aspect-ratio drift. It is not CLIP and not a
learned metric — it is a defensible, explainable number whose components are stored
in the manifest, so a grading decision can be argued with.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SimilarityReport:
    score: float
    components: dict[str, float]
    width: int
    height: int

    def as_dict(self) -> dict[str, float]:
        components = {key: round(value, 4) for key, value in self.components.items()}
        return {"score": round(self.score, 4), **components}


def _load_gray(path: Path, size: int):
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        gray = image.convert("L")
        resized = gray.resize((size, size), Image.Resampling.LANCZOS)
        array = np.asarray(resized, dtype="float32") / 255.0
    return array, image.size


def compare_images(reference: Path, candidate: Path, *, size: int = 256) -> SimilarityReport:
    import numpy as np

    ref, ref_size = _load_gray(reference, size)
    cand, cand_size = _load_gray(candidate, size)

    ref_norm = (ref - ref.mean()) / (ref.std() + 1e-6)
    cand_norm = (cand - cand.mean()) / (cand.std() + 1e-6)
    correlation = float((ref_norm * cand_norm).mean())
    mean_abs_difference = float(np.abs(ref - cand).mean())

    def edge_energy(array):
        gy, gx = np.gradient(array)
        return float(np.hypot(gx, gy).mean())

    ref_edge, cand_edge = edge_energy(ref), edge_energy(cand)
    edge_agreement = 1.0 - abs(ref_edge - cand_edge) / (max(ref_edge, cand_edge) + 1e-6)

    ink_ref = float((ref < 0.85).mean())
    ink_cand = float((cand < 0.85).mean())
    ink_agreement = 1.0 - abs(ink_ref - ink_cand) / (max(ink_ref, ink_cand) + 1e-6)

    base = (
        0.50 * max(correlation, 0.0)
        + 0.25 * (1.0 - mean_abs_difference)
        + 0.15 * max(edge_agreement, 0.0)
        + 0.10 * max(ink_agreement, 0.0)
    )
    ref_ratio = ref_size[0] / max(ref_size[1], 1)
    cand_ratio = cand_size[0] / max(cand_size[1], 1)
    aspect_penalty = float(np.exp(-abs(np.log(cand_ratio / ref_ratio + 1e-9))))
    score = float(max(0.0, min(1.0, base * (0.5 + 0.5 * aspect_penalty))))
    return SimilarityReport(
        score=score,
        components={
            "correlation": max(correlation, 0.0),
            "mean_abs_difference": mean_abs_difference,
            "edge_agreement": max(edge_agreement, 0.0),
            "ink_agreement": max(ink_agreement, 0.0),
            "aspect_ratio_ref": ref_ratio,
            "aspect_ratio_candidate": cand_ratio,
            "aspect_penalty": aspect_penalty,
        },
        width=int(cand_size[0]),
        height=int(cand_size[1]),
    )


def raster_candidates(paths: list[Path]) -> list[Path]:
    allowed = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    return [path for path in paths if path.suffix.lower() in allowed]
