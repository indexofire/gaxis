"""Select boundary cases from a judged corpus for judge calibration.

The golden set answers "can the judge separate good from bad". Boundary cases answer
"where is the line, and which direction is the judge biased". They are cheaper for a
human to label (keep / borderline / drop) than a total ranking.

    pixi run python scripts/boundary_set.py --judged data/corpus/wechat-series/judged \
        --out data/corpus/boundary --limit 24
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image

from gaxis.design import build_candidate_sheet, dhash, hamming


def _size(path: Path) -> tuple[int, int]:
    with Image.open(path) as handle:
        return handle.size


def _pick(records: list[dict], limit: int) -> tuple[list[dict], list[str]]:
    """Stratified sample with quotas: boundary, suspect type, low-res, false-negative."""
    chosen: list[dict] = []
    reasons: dict[str, str] = {}

    def take(record: dict, reason: str) -> bool:
        if record["file"] in reasons or len(chosen) >= limit:
            return False
        reasons[record["file"]] = reason
        chosen.append(record)
        return True

    def score_of(record: dict) -> float:
        return float(record["score"])

    mid = [record for record in records if 0.45 <= score_of(record) < 0.60]
    # sort ascending so the lowest boundary scores are included, not just 0.55s
    mid.sort(key=score_of)
    low_edge = [record for record in mid if score_of(record) < 0.50]
    high_edge = [record for record in mid if score_of(record) >= 0.50]
    for record in low_edge[:4]:
        take(record, "mid-band (low edge, 0.45-0.50)")
    for record in high_edge[:4]:
        take(record, "mid-band (0.50-0.60)")

    suspect = [
        record
        for record in records
        if score_of(record) >= 0.60
        and (
            (record.get("features") or {}).get("photo_like")
            or not (record.get("features") or {}).get("chart_like")
        )
    ]
    for record in suspect[:5]:
        take(record, "suspect type (photo/illustration scored high)")

    huge = []
    for record in records:
        try:
            width, height = _size(Path(record["file"]))
        except Exception as exc:  # broken export in a curated folder
            print(f"skip size {record['file']}: {exc}")
            continue
        if max(width, height) > 2400 and score_of(record) >= 0.60:
            huge.append((max(width, height), record, f"{width}x{height}"))
    huge.sort(key=lambda item: item[0], reverse=True)
    for _, record, size in huge[:4]:
        take(record, f"very large panel ({size}) — 89 mm legibility risk")

    reject_charts = [
        record
        for record in records
        if score_of(record) < 0.45 and (record.get("features") or {}).get("chart_like")
    ]
    for record in reject_charts[:4]:
        take(record, "reject but chart-like (false-negative probe)")

    remaining = [record for record in records if record["file"] not in reasons]
    if remaining:
        step = max(1, len(remaining) // max(1, limit - len(chosen)))
        for record in remaining[::step]:
            take(record, f"spread sample (score {record['score']:.2f})")
    return chosen[:limit], [reasons[record["file"]] for record in chosen[:limit]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judged", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--max-distance", type=int, default=6)
    args = parser.parse_args()

    payload = json.loads((args.judged / "judgements.json").read_text())
    records = [record for record in payload["records"] if "score" in record]
    records.sort(key=lambda record: record["score"], reverse=True)

    deduped: list[dict] = []
    fingerprints: list[int] = []
    for record in records:
        try:
            fingerprint = dhash(Path(record["file"]))
        except Exception as exc:  # unreadable files are not curated
            print(f"skip {record['file']}: {exc}")
            continue
        if any(hamming(fingerprint, other) <= args.max_distance for other in fingerprints):
            continue
        fingerprints.append(fingerprint)
        deduped.append(record)

    chosen, reasons = _pick(deduped, args.limit)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    rows = ["n,file,source,score,aesthetic,visualization,reason,keep,borderline,drop"]
    paths: list[Path] = []
    for index, (record, reason) in enumerate(zip(chosen, reasons, strict=True), start=1):
        source = Path(record["file"])
        target = out / f"case-{index:02d}{source.suffix.lower()}"
        shutil.copyfile(source, target)
        paths.append(target)
        rows.append(
            f"{index},{target.name},{source},{record['score']},{record['aesthetic']},"
            f'{record["visualization"]},"{reason}",,,'
        )
    (out / "index.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    _, _, contact = build_candidate_sheet(paths, out_dir=out)
    print(f"boundary cases: {len(paths)} -> {contact}")
    for row in rows[1:]:
        print("  ", row.split(",")[1], "|", row.split(",")[3], "|", row.split('"')[1])


if __name__ == "__main__":
    main()
