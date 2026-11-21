"""Build a numbered contact sheet for the top/bottom N figures of a judged corpus.

pixi run python scripts/ranked_sheet.py data/corpus/wechat-series/judged --top 30 --bottom 10
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from gaxis.design import build_candidate_sheet, dedupe_perceptual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("judged_dir", type=Path)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--bottom", type=int, default=10)
    args = parser.parse_args()

    rows = list(csv.DictReader((args.judged_dir / "judgements.csv").open()))
    resolved = [Path(row["file"]) for row in rows]
    resolved = [path for path in resolved if path.is_file()]
    before = len(resolved)
    resolved = dedupe_perceptual(resolved)
    print(f"perceptual dedupe: {before} -> {len(resolved)} figures")
    for label, selection in (("top", resolved[: args.top]), ("bottom", resolved[-args.bottom :])):
        if not selection:
            continue
        _, _, contact = build_candidate_sheet(selection, out_dir=args.judged_dir / f"{label}-sheet")
        print(f"{label}: {len(selection)} figure(s) -> {contact}")


if __name__ == "__main__":
    main()
