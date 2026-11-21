"""Split style-reference plates into single-figure candidates for design calibration.

    pixi run python scripts/split_plates.py \
        --plates data/corpus/boundary data/corpus/golden/plates \
        --out data/corpus/single-figures --limit 60
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gaxis.design import build_candidate_sheet, split_plate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plates", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    rows = ["n,file,plate,block,width,height"]
    paths: list[Path] = []
    for folder in args.plates:
        for plate in sorted(folder.glob("*.png")) + sorted(folder.glob("*.jpg")):
            if plate.stem.startswith(("contact-sheet", "sheet", "candidate", "good")):
                continue
            crops = split_plate(plate, out, stem=plate.stem)
            for index, crop in enumerate(crops, start=1):
                if len(paths) >= args.limit:
                    break
                from PIL import Image

                with Image.open(crop) as handle:
                    width, height = handle.size
                paths.append(crop)
                rows.append(f"{len(paths)},{crop.name},{plate.name},{index},{width},{height}")
            if len(paths) >= args.limit:
                break
        if len(paths) >= args.limit:
            break
    (out / "index.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    _, _, contact = build_candidate_sheet(paths, out_dir=out / "sheet", limit=args.limit)
    print(f"single-figure candidates: {len(paths)} -> {contact}")
    print(f"index: {out / 'index.csv'}")


if __name__ == "__main__":
    main()
