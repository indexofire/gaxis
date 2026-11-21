"""Design judgement: a port, because aesthetics is not a pixel formula.

`HeuristicJudge` is the offline fallback: it scores only the defensible objective
signals (palette discipline, whitespace, legibility, caption rubric). It is a gate,
not a taste model.

`VisionJudge` asks a vision-language model to score the figure against the same
rubric a human uses, and stores the rationale. That is the only way to judge
"beautiful / well-designed" at corpus scale; it must be calibrated against human
ranks before its thresholds are trusted (see docs/design-quality.md).
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from .design import analyse_design
from .models.paper import DesignQuality

MAX_VISION_SIDE = 768


def _prepare_image(raw: bytes, max_side: int = MAX_VISION_SIDE) -> bytes:
    """Downscale before sending: a 2000-px page costs far more tokens than it adds.

    1024 px keeps axis labels and panel letters readable while cutting vision tokens
    several-fold, which matters on CPU-only inference.
    """
    import io as _io

    from PIL import Image

    with Image.open(_io.BytesIO(raw)) as handle:
        rgb = handle.convert("RGB")
        scale = max_side / max(rgb.size)
        if scale < 1:
            rgb = rgb.resize((max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale))))
        buffer = _io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


RUBRIC = """\
You are reviewing a figure for a microbiology paper. First classify WHAT the image is,
then score it. Classification is decisive: a beautiful illustration is still not a data
figure, and a micrograph panel is not a chart.

CATEGORY (choose exactly one):
- "chart": data visualization built from quantitative encodings — bars, lines, scatter,
  box/violin, heatmap, dot plot, forest plot, survival curve, UMAP/t-SNE, ROC, enrichment
  bar/lollipop, with axes and labels.
- "mixed": quantitative panels are essential to the figure (two or more bar/line/scatter/
  heatmap/flow panels), even when a schematic or a micrograph is prominent. A well-designed
  composite that mixes a model diagram with several data panels is MIXED, not schematic.
- "schematic": illustration / diagram / model / workflow / graphical abstract.
- "micrograph": microscopy, histology, blots or photographic panels as the main content.
- "plate": a montage of several complete figures stacked or tiled.

SCORING 0-10 each:

AESTHETIC if chart or mixed: palette discipline (3-8 deliberate, colour-blind-safe colours,
no rainbow), whitespace, alignment, typographic consistency, no chart junk (heavy grids,
3D, shadows, gradients). Dense multi-panel figures are fine when labels stay readable;
do NOT punish information richness by itself.

VISUALIZATION if chart or mixed: correct chart type for the data, complete axis labels with
units, uncertainty shown (error bars / CI / box / shaded band), legible at 89 mm print
width, panels labelled and ordered. A chart that is illegible at print size loses points;
a dense but legible one does not.

If category is "schematic" or "micrograph": score BOTH axes at most 3, because the image is
an illustration or photo panel rather than a reusable data figure, and say so in the rationale.

If category is "plate": score it as a figure montage — completeness, palette consistency and
layout matter, but do not reward it for being large. A well-designed plate is a useful style
reference even when its individual panels cannot be reused as a single template.

Return ONLY JSON:
{"category": "<one of the categories>", "aesthetic": <0-10>, "visualization": <0-10>,
 "rationale": ["short point", "short point", "short point"]}
"""


class DesignJudgeError(RuntimeError):
    pass


class DesignJudge(Protocol):
    name: str

    def judge(
        self, image: bytes | Path, *, caption: str = "", label_font_pt: float | None = None
    ) -> DesignQuality: ...


class HeuristicJudge:
    """Offline rubric: objective signals only, no taste claim."""

    name = "heuristic"

    def judge(
        self, image: bytes | Path, *, caption: str = "", label_font_pt: float | None = None
    ) -> DesignQuality:
        return analyse_design(image, caption=caption, label_font_pt=label_font_pt)


class VisionJudge:
    """OpenAI-compatible chat-completions vision judge (no vendor SDK)."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str = "OPENAI_API_KEY",
        timeout_s: float = 300.0,
        max_side: int = MAX_VISION_SIDE,
        retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = os.environ.get(api_key_env, "")
        self.timeout_s = timeout_s
        self.max_side = max_side
        self.retries = max(0, retries)
        self.name = f"vision:{model}"

    def _payload(self, image: bytes | Path, caption: str) -> dict[str, Any]:
        raw = image.read_bytes() if isinstance(image, Path) else image
        encoded = base64.b64encode(_prepare_image(raw, self.max_side)).decode()
        text = RUBRIC + ("\n\nFigure caption:\n" + caption if caption else "")
        return {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
        }

    def judge(
        self, image: bytes | Path, *, caption: str = "", label_font_pt: float | None = None
    ) -> DesignQuality:
        local = any(host in self.base_url for host in ("127.0.0.1", "localhost"))
        if not self.api_key and not local:
            raise DesignJudgeError("vision judge has no API key in the configured env var")
        request = urllib.request.Request(  # noqa: S310 - configured https endpoint
            f"{self.base_url}/chat/completions",
            data=json.dumps(self._payload(image, caption)).encode(),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
        )
        body: dict[str, Any] = {}
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310
                    body = json.load(response)
                break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
        else:
            raise DesignJudgeError(f"vision judge request failed: {last_error}")
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DesignJudgeError(f"unexpected vision response: {body}") from exc
        payload = parse_judgement(content)
        analysed = analyse_design(image, caption=caption, label_font_pt=label_font_pt)
        category = payload.get("category") or "unknown"
        if analysed.features.plate_like:
            category = "plate"
        return DesignQuality(
            model=self.name,
            method=self.name,
            aesthetic=payload["aesthetic"] / 10,
            visualization=payload["visualization"] / 10,
            score=(payload["aesthetic"] + payload["visualization"]) / 20,
            notes=payload["rationale"],
            features=analysed.features,
            category=category,  # type: ignore[arg-type]
        )


def parse_judgement(content: str) -> dict[str, Any]:
    """Tolerant JSON extraction: models like to wrap answers in prose or fences."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise DesignJudgeError(f"vision judge returned no JSON: {content[:200]}")
    try:
        payload = json.loads(text[start : end + 1])
        aesthetic = float(payload["aesthetic"])
        visualization = float(payload["visualization"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise DesignJudgeError(f"invalid judgement payload: {content[:200]}") from exc
    rationale = payload.get("rationale") or []
    if not isinstance(rationale, list):
        rationale = [str(rationale)]
    allowed = {"chart", "mixed", "schematic", "micrograph", "plate", "unknown"}
    category = str(payload.get("category", "unknown")).strip().lower()
    return {
        "aesthetic": max(0.0, min(10.0, aesthetic)),
        "visualization": max(0.0, min(10.0, visualization)),
        "rationale": [str(item)[:200] for item in rationale][:5],
        "category": category if category in allowed else "unknown",
    }


def build_judge(settings: Any) -> DesignJudge:
    """Choose the judge from config; a broken vision setup falls back explicitly."""
    from .config import DesignSettings

    design: DesignSettings = settings.config.design
    if design.judge == "vision":
        judge = VisionJudge(
            base_url=design.base_url,
            model=design.model,
            api_key_env=design.api_key_env,
            timeout_s=design.timeout_s,
            max_side=design.max_side,
            retries=design.retries,
        )
        local = any(host in design.base_url for host in ("127.0.0.1", "localhost"))
        if judge.api_key or local:
            return judge
    return HeuristicJudge()
