"""Publication-grade lint: file-level checks that work for both render backends.

Language-agnostic on purpose — a PDF produced by matplotlib and one produced by
cairo_pdf are judged by the same rules.
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path

from ..models.lint import LintIssue, LintReport, Severity
from ..models.spec import ChartSpec
from .palettes import get_palette
from .presets import Preset
from .rc import resolve_font

VECTOR_FORMATS = {"pdf", "svg"}
MIN_DPI = 300
GEOMETRY_TOLERANCE = 0.15
_MEDIABOX_RE = re.compile(rb"/MediaBox\s*\[\s*([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)")
_FONT_NAME_RE = re.compile(r"font-family\s*[:=]\s*[\"']?([A-Za-z0-9 _\-]+)")
_PDF_FONT_RE = re.compile(rb"/BaseFont\s*/([A-Za-z0-9+\-_,]+)")
_UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72.0, "px": 25.4 / 96.0}


def _png_info(data: bytes) -> tuple[float | None, float | None, int | None]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None, None, None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    dpi: int | None = None
    position = 8
    while position + 8 <= len(data):
        length = int.from_bytes(data[position : position + 4], "big")
        chunk = data[position + 4 : position + 8]
        if chunk == b"pHYs" and length >= 9:
            ppu_x = int.from_bytes(data[position + 8 : position + 12], "big")
            unit = data[position + 16]
            if unit == 1 and ppu_x:
                dpi = round(ppu_x * 0.0254)
            break
        position += 12 + length
    return width, height, dpi


def _inflate(data: bytes) -> bytes:
    """Concatenate the raw file with every zlib-decodable stream (cairo compresses MediaBox)."""
    blobs = [data]
    for match in re.finditer(rb"stream\r?\n", data):
        end = data.find(b"endstream", match.end())
        if end < 0:
            continue
        try:
            blobs.append(zlib.decompress(data[match.end() : end].rstrip(b"\r\n")))
        except zlib.error:
            continue
    return b"\n".join(blobs)


def _pdf_info(data: bytes) -> tuple[float | None, float | None, set[str], bool]:
    width_mm = height_mm = None
    data = _inflate(data)
    match = _MEDIABOX_RE.search(data)
    if match:
        x0, y0, x1, y1 = (float(match.group(i)) for i in range(1, 5))
        width_mm = abs(x1 - x0) * _UNIT_TO_MM["pt"]
        height_mm = abs(y1 - y0) * _UNIT_TO_MM["pt"]
    fonts = {m.group(1).decode("latin-1") for m in _PDF_FONT_RE.finditer(data)}
    return width_mm, height_mm, fonts, b"/Type3" in data


def _parse_svg_length(value: str) -> float | None:
    match = re.match(r"^\s*([\d.]+)\s*([a-z%]*)\s*$", value)
    if not match:
        return None
    number, unit = float(match.group(1)), match.group(2) or "px"
    return number * _UNIT_TO_MM.get(unit, _UNIT_TO_MM["px"])


def _svg_info(data: str) -> tuple[float | None, float | None, set[str]]:
    root = re.search(r"<svg[^>]*>", data)
    width = height = None
    if root:
        tag = root.group(0)
        w = re.search(r'\bwidth="([^"]+)"', tag)
        h = re.search(r'\bheight="([^"]+)"', tag)
        width = _parse_svg_length(w.group(1)) if w else None
        height = _parse_svg_length(h.group(1)) if h else None
    return width, height, set(_FONT_NAME_RE.findall(data))


def _geometry_issue(
    actual_w: float | None,
    actual_h: float | None,
    expected_w: float,
    expected_h: float,
    subject: str,
) -> list[LintIssue]:
    if actual_w is None or actual_h is None or not expected_w or not expected_h:
        return []
    issues: list[LintIssue] = []
    for axis, actual, expected in (
        ("width", actual_w, expected_w),
        ("height", actual_h, expected_h),
    ):
        delta = abs(actual - expected) / expected
        if delta > GEOMETRY_TOLERANCE:
            issues.append(
                LintIssue(
                    code="L006",
                    severity=Severity.error,
                    message=(
                        f"{axis} {actual:.1f} mm deviates {delta:.0%} from the journal "
                        f"geometry ({expected:.1f} mm)"
                    ),
                    subject=subject,
                )
            )
        elif delta > 0.03:
            issues.append(
                LintIssue(
                    code="L006",
                    severity=Severity.info,
                    message=f"{axis} {actual:.1f} mm vs {expected:.1f} mm target ({delta:.0%})",
                    subject=subject,
                )
            )
    return issues


def lint_outputs(
    paths: list[Path],
    *,
    preset: Preset,
    spec: ChartSpec,
    expected_width_mm: float,
    expected_height_mm: float,
) -> LintReport:
    issues: list[LintIssue] = []
    existing = [p for p in paths if p.is_file() and p.stat().st_size > 0]
    if len(existing) != len(paths):
        missing = [str(p.name) for p in paths if p not in existing]
        issues.append(
            LintIssue(
                code="L001", severity=Severity.error, message=f"missing output files: {missing}"
            )
        )
    formats = {p.suffix.lower().lstrip(".") for p in existing}
    if preset.vector_required and not (formats & VECTOR_FORMATS):
        issues.append(
            LintIssue(
                code="L002",
                severity=Severity.error,
                message=(
                    f"no vector output ({sorted(VECTOR_FORMATS)}); raster-only figures are refused"
                ),
            )
        )

    expected_font = resolve_font(tuple(preset.font_family))
    for path in existing:
        suffix = path.suffix.lower()
        subject = path.name
        data = path.read_bytes()
        if len(data) < 2048:
            issues.append(
                LintIssue(
                    code="L009",
                    severity=Severity.warning,
                    message=f"suspiciously small file ({len(data)} bytes) — blank figure?",
                    subject=subject,
                )
            )
        if suffix == ".pdf":
            width_mm, height_mm, fonts, has_type3 = _pdf_info(data)
            issues.extend(
                _geometry_issue(width_mm, height_mm, expected_width_mm, expected_height_mm, subject)
            )
            if has_type3:
                issues.append(
                    LintIssue(
                        code="L004",
                        severity=Severity.error,
                        message=(
                            "PDF contains Type 3 fonts; journals require "
                            "embedded TrueType (Type 42)"
                        ),
                        subject=subject,
                    )
                )
            if expected_font and not any(expected_font.split()[0] in f for f in fonts):
                issues.append(
                    LintIssue(
                        code="L005",
                        severity=Severity.warning,
                        message=(
                            f"PDF fonts {sorted(fonts)} do not include the preset font "
                            f"'{expected_font}' (embedded?)"
                        ),
                        subject=subject,
                    )
                )
        elif suffix == ".svg":
            width_mm, height_mm, fonts = _svg_info(data.decode("utf-8", errors="replace"))
            issues.extend(
                _geometry_issue(width_mm, height_mm, expected_width_mm, expected_height_mm, subject)
            )
            if expected_font and fonts and not any(expected_font.split()[0] in f for f in fonts):
                issues.append(
                    LintIssue(
                        code="L005",
                        severity=Severity.warning,
                        message=(
                            f"SVG text uses {sorted(fonts)[:4]}, preset expects '{expected_font}'"
                        ),
                        subject=subject,
                    )
                )
        elif suffix == ".png":
            _, _, dpi = _png_info(data)
            if dpi is not None and dpi < MIN_DPI:
                issues.append(
                    LintIssue(
                        code="L003",
                        severity=Severity.error,
                        message=f"{dpi} dpi is below the {MIN_DPI} dpi minimum",
                        subject=subject,
                    )
                )
            elif dpi is not None and dpi < preset.dpi:
                issues.append(
                    LintIssue(
                        code="L003",
                        severity=Severity.info,
                        message=f"{dpi} dpi is below the preset's {preset.dpi} dpi",
                        subject=subject,
                    )
                )

    if not get_palette(spec.palette or preset.palette).colorblind_safe:
        issues.append(
            LintIssue(
                code="L007",
                severity=Severity.warning,
                message=(
                    f"palette '{spec.palette or preset.palette}' is not colour-blind safe; "
                    "journals increasingly require one"
                ),
            )
        )

    svg_text = "".join(
        p.read_text(encoding="utf-8", errors="replace") for p in existing if p.suffix == ".svg"
    )
    for code, expected in (("L008", spec.title), ("L008", spec.xlabel), ("L008", spec.ylabel)):
        if expected and svg_text and expected not in svg_text:
            issues.append(
                LintIssue(
                    code=code,
                    severity=Severity.warning,
                    message=f"label '{expected}' not found in the SVG text layer",
                )
            )
    return LintReport(issues=issues)


def measure_output(path: Path) -> tuple[float | None, float | None, int | None]:
    """(width_mm, height_mm, dpi) for a rendered file; dpi is None for vector formats."""
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        width_mm, height_mm, _, _ = _pdf_info(data)
        return width_mm, height_mm, None
    if suffix == ".svg":
        width_mm, height_mm, _ = _svg_info(data.decode("utf-8", errors="replace"))
        return width_mm, height_mm, None
    if suffix == ".png":
        width_px, height_px, dpi = _png_info(data)
        if width_px is None or height_px is None:
            return None, None, dpi
        effective = dpi or 96
        return width_px / effective * 25.4, height_px / effective * 25.4, dpi
    return None, None, None
