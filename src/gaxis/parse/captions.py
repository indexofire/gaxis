"""Caption and citation heuristics — pure text functions, no PDF library needed.

Journal captions follow a stable shape ("Fig. 3. …" / "Figure 3A: …"), and body
text references them ("as shown in Fig. 3"). Both are cheap to detect and are what
turns a pile of text blocks into "figure 3 with its caption and citing paragraph".
"""

from __future__ import annotations

import re
from collections.abc import Iterable

CAPTION_RE = re.compile(
    # Nature-family captions use a vertical bar ("Fig. 1 | Title"); a closing bracket is
    # deliberately NOT a delimiter because body references look like "Fig. 5a). …"
    r"^\s*(?:fig(?:ure)?\.?|图)\s*(\d{1,2})\s*([A-Za-z])?\s*([.:：、|—–])?\s*(.*)$",
    re.IGNORECASE,
)
_MENTION_RE = re.compile(r"(?:fig(?:ure)?s?\.?|图)\s*(\d{1,2})(?![0-9])", re.IGNORECASE)
_SUPPLEMENTARY_RE = re.compile(r"^\s*(?:fig(?:ure)?\.?|图)\s*[Ss]\d", re.IGNORECASE)
_HYPHEN_BREAK = re.compile(r"([a-z])-\s+([a-z])")


def parse_label(text: str) -> tuple[int, str] | None:
    """``"Fig. 3. Grouped bars…"`` -> ``(3, "Grouped bars…")``; supplementary is ignored."""
    if _SUPPLEMENTARY_RE.match(text):
        return None
    match = CAPTION_RE.match(text)
    if not match:
        return None
    delimiter, rest = match.group(3), match.group(4).strip()
    # "Fig. 2 in a companion paper" is a citation, not a caption: require a
    # delimiter, an empty remainder, or a capitalised/bracketed continuation.
    cjk = "\u4e00" <= (rest[0] if rest else " ") <= "\u9fff"
    if (
        not delimiter
        and rest
        and not (rest[0].isupper() or rest[0].isdigit() or rest[0] in "([【" or cjk)
    ):
        return None
    return int(match.group(1)), rest


def is_caption_start(text: str) -> bool:
    return parse_label(text) is not None


def clean_text(text: str) -> str:
    """Normalise whitespace and undo end-of-line hyphenation."""
    joined = _HYPHEN_BREAK.sub(r"\1\2", text)
    return re.sub(r"\s+", " ", joined).strip()


def join_blocks(blocks: Iterable[str]) -> str:
    return clean_text(" ".join(block.strip() for block in blocks if block.strip()))


def mentions_figure(text: str, number: int) -> bool:
    return any(int(match.group(1)) == number for match in _MENTION_RE.finditer(text))


def extract_citations(blocks: Iterable[str], number: int, *, limit: int = 3) -> list[str]:
    """Body paragraphs that cite the figure, in document order."""
    found: list[str] = []
    for block in blocks:
        cleaned = clean_text(block)
        if not cleaned or is_caption_start(cleaned):
            continue
        if mentions_figure(cleaned, number):
            found.append(cleaned)
        if len(found) >= limit:
            break
    return found


def figure_ref(number: int, letter: str | None = None) -> str:
    return f"Fig. {number}{letter.upper() if letter else ''}".strip()
