"""Regenerate tests/contract_snapshot.json after an intentional contract change.

Bump CONTRACT_VERSION at the same time (and the changelog entry).
"""

from __future__ import annotations

import json
from pathlib import Path

from gaxis.models.tools import TOOL_SPECS

CONTRACT_VERSION = "v2.8"

snapshot = {
    "contract_version": CONTRACT_VERSION,
    "tools": {
        spec.name: {
            "data_class": str(spec.data_class),
            "inputs": sorted(spec.input_schema.get("properties", {})),
            "outputs": sorted(spec.output_schema.get("properties", {})),
        }
        for spec in TOOL_SPECS
    },
}
target = Path(__file__).resolve().parents[1] / "tests" / "contract_snapshot.json"
target.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
print(f"wrote {target} (contract {CONTRACT_VERSION})")
