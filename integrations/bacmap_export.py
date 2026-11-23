#!/usr/bin/env python3
"""Reference bacmap -> gaxis export (host-side, not part of the gaxis kernel).

bacmap already has AMR calls, species, serotype and MLST in its results tree. This
script turns one bacmap run into the two files gaxis analysis/render expects:

    amr_long.csv   sample,gene,gene_class   (one observed gene per sample)
    metadata.csv   sample,species,serotype  (tip metadata / grouping)

It imports nothing from bacmap or gaxis. Run it next to a bacmap results run.

    python integrations/bacmap_export.py --run-dir ~/.local/share/bacmap/results/runs/<id> \
        --out data/bacmap-export
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_amrfinder(path: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for record in reader:
            gene = (record.get("Element symbol") or "").strip()
            klass = (record.get("Class") or "").strip()
            if not gene or gene == "NA":
                continue
            rows.append((gene, klass or "unclassified", (record.get("Type") or "").strip()))
    return rows


def read_summary(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    steps = payload.get("steps", {}) if isinstance(payload, dict) else {}
    species = steps.get("species", {})
    if isinstance(species, dict):
        species_name = str(species.get("species") or species.get("verdict") or "")
    else:
        species_name = str(species or "")
    serotype = steps.get("serotype", {})
    if isinstance(serotype, dict):
        sero = str(serotype.get("value") or serotype.get("sistr") or "")
    else:
        sero = str(serotype or "")
    return {"species": species_name, "serotype": sero}


def export(run_dir: Path, out_dir: Path) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    long_rows: list[tuple[str, str, str]] = []
    metadata: list[dict[str, str]] = []
    samples = sorted(
        path.name for path in run_dir.iterdir() if path.is_dir() and path.name.startswith("26")
    )
    for sample in samples:
        amr = run_dir / sample / "amr" / "amrfinderplus.tsv"
        if not amr.is_file():
            continue
        seen: set[str] = set()
        for gene, klass, _kind in read_amrfinder(amr):
            if gene in seen:
                continue
            seen.add(gene)
            long_rows.append((sample, gene, klass))
        summary = next(iter((run_dir / sample / "report").glob("*_summary.json")), None)
        info = read_summary(summary) if summary else {}
        metadata.append(
            {
                "sample": sample,
                "species": info.get("species", ""),
                "serotype": info.get("serotype", ""),
            }
        )

    long_path = out_dir / "amr_long.csv"
    with long_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample", "gene", "gene_class"])
        writer.writerows(long_rows)
    metadata_path = out_dir / "metadata.csv"
    with metadata_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample", "species", "serotype"])
        writer.writeheader()
        writer.writerows(metadata)

    manifest = {
        "run_dir": str(run_dir),
        "samples": len(metadata),
        "amr_rows": len(long_rows),
        "outputs": {"amr_long": str(long_path), "metadata": str(metadata_path)},
    }
    (out_dir / "export.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = export(args.run_dir.expanduser().resolve(), args.out.expanduser().resolve())
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
