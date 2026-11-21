"""Curate a judged figure corpus: perceptual dedupe, contact sheets, final selection.

    # 1) dedupe + contact sheets for review
    pixi run python scripts/curate_corpus.py dedupe --judged data/corpus/wechat-series/judged \
        --out data/corpus/wechat-dedup --sheets-of 24 --max-score 0.6

    # 2) keep the numbered items you approved, with provenance
    pixi run python scripts/curate_corpus.py select --work data/corpus/wechat-dedup \
        --select 1-8,11,14-19 --out data/corpus/wechat-curated
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
from pathlib import Path

from gaxis.design import build_candidate_sheet, dhash, hamming

logger = logging.getLogger(__name__)


def _parse_selection(text: str) -> list[int]:
    numbers: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            numbers.extend(range(int(start), int(end) + 1))
        else:
            numbers.append(int(part))
    return numbers


def dedupe(args: argparse.Namespace) -> None:
    payload = json.loads((args.judged / "judgements.json").read_text())
    records = [record for record in payload["records"] if "score" in record]
    records.sort(key=lambda record: record["score"], reverse=True)
    kept: list[dict] = []
    fingerprints: list[int] = []
    for record in records:
        path = Path(record["file"])
        try:
            fingerprint = dhash(path)
        except Exception as exc:
            logger.warning("skipping unreadable figure %s: %s", path, exc)
            continue
        if any(hamming(fingerprint, other) <= args.max_distance for other in fingerprints):
            continue
        fingerprints.append(fingerprint)
        kept.append(record)
    if args.max_score is None:
        pass
    selected = [record for record in kept if record["score"] >= (args.min_score or 0.0)][
        0 : args.limit
    ]
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    rows = ["n,file,source,score,aesthetic,visualization,method"]
    paths: list[Path] = []
    for index, record in enumerate(selected, start=1):
        source = Path(record["file"])
        target = out / f"fig-{index:03d}{source.suffix.lower()}"
        shutil.copyfile(source, target)
        paths.append(target)
        rows.append(
            f"{index},{target.name},{source},"
            f"{record['score']},{record['aesthetic']},{record['visualization']},{record['method']}"
        )
    (out / "index.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    for start in range(0, len(paths), args.sheets_of):
        chunk = paths[start : start + args.sheets_of]
        _, _, contact = build_candidate_sheet(
            chunk, out_dir=out / "sheets" / f"sheet-{start // args.sheets_of + 1:02d}"
        )
        print(f"sheet {start // args.sheets_of + 1}: {len(chunk)} figures -> {contact}")
    print(f"deduped corpus: {len(paths)} figures -> {out}")


def select(args: argparse.Namespace) -> None:
    index = list(csv.DictReader((args.work / "index.csv").open()))
    wanted = set(_parse_selection(args.select))
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    rows = ["n,file,source,score,aesthetic,visualization"]
    paths: list[Path] = []
    for row in index:
        number = int(row["n"])
        if number not in wanted:
            continue
        source = args.work / row["file"]
        target = out / f"good-{len(paths) + 1:02d}{source.suffix.lower()}"
        shutil.copyfile(source, target)
        paths.append(target)
        rows.append(
            f"{len(paths)},{target.name},{row['source']},"
            f"{row['score']},{row['aesthetic']},{row['visualization']}"
        )
    (out / "index.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    _, _, contact = build_candidate_sheet(paths, out_dir=out)
    print(f"selected: {len(paths)} figures -> {contact}")
    print(f"index: {out / 'index.csv'}")


def library(args: argparse.Namespace) -> None:
    """Bucket a judged corpus into gold/dense/reject, deduped, with index + sheets."""
    payload = json.loads((args.judged / "judgements.json").read_text())
    records = [record for record in payload["records"] if "score" in record]
    records.sort(key=lambda record: record["score"], reverse=True)
    kept: list[dict] = []
    fingerprints: list[int] = []
    for record in records:
        path = Path(record["file"])
        try:
            fingerprint = dhash(path)
        except Exception as exc:  # unreadable files are skipped
            logger.warning("skipping unreadable figure %s: %s", path, exc)
            continue
        if any(hamming(fingerprint, other) <= args.max_distance for other in fingerprints):
            continue
        fingerprints.append(fingerprint)
        kept.append(record)

    buckets: dict[str, list[dict]] = {"gold": [], "dense": [], "reject": []}
    for record in kept:
        score = record["score"]
        tier = "gold" if score >= args.gold else "dense" if score >= args.dense else "reject"
        buckets[tier].append(record)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    summary = ["tier,count,mean_score,min_score,max_score"]
    for tier, items in buckets.items():
        folder = out / tier
        folder.mkdir(exist_ok=True)
        paths: list[Path] = []
        rows = ["n,file,source,score,aesthetic,visualization"]
        for index, record in enumerate(items, start=1):
            source = Path(record["file"])
            target = folder / f"{tier}-{index:03d}{source.suffix.lower()}"
            shutil.copyfile(source, target)
            paths.append(target)
            rows.append(
                f"{index},{target.name},{source},{record['score']},"
                f"{record['aesthetic']},{record['visualization']}"
            )
        (folder / "index.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        for start in range(0, len(paths), args.sheets_of):
            chunk = paths[start : start + args.sheets_of]
            _, _, contact = build_candidate_sheet(
                chunk, out_dir=folder / "sheets" / f"sheet-{start // args.sheets_of + 1:02d}"
            )
            print(
                f"{tier}: sheet {start // args.sheets_of + 1} ({len(chunk)} figures) -> {contact}"
            )
        scores = [record["score"] for record in items]
        if scores:
            summary.append(
                f"{tier},{len(items)},{sum(scores) / len(scores):.3f},"
                f"{min(scores):.3f},{max(scores):.3f}"
            )
        else:
            summary.append(f"{tier},0,,,")
    (out / "summary.csv").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("dedupe")
    d.add_argument("--judged", type=Path, required=True)
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("--sheets-of", type=int, default=24)
    d.add_argument("--min-score", type=float, default=0.0)
    d.add_argument("--max-score", type=float, default=None)
    d.add_argument("--max-distance", type=int, default=6)
    d.add_argument("--limit", type=int, default=200)
    d.set_defaults(func=dedupe)
    lib = sub.add_parser("library")
    lib.add_argument("--judged", type=Path, required=True)
    lib.add_argument("--out", type=Path, required=True)
    lib.add_argument("--gold", type=float, default=0.55)
    lib.add_argument("--dense", type=float, default=0.45)
    lib.add_argument("--max-distance", type=int, default=6)
    lib.add_argument("--sheets-of", type=int, default=24)
    lib.set_defaults(func=library)
    s = sub.add_parser("select")
    s.add_argument("--work", type=Path, required=True)
    s.add_argument("--select", required=True)
    s.add_argument("--out", type=Path, required=True)
    s.set_defaults(func=select)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
