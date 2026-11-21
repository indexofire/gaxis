#!/usr/bin/env bash
# Initialize a project-local gbrain (idempotent).
#
# Database-only on purpose: gaxis already owns the asset store (files + manifests),
# so gbrain is an index, not a second copy of the figures. Nothing is written to
# ~/.gbrain — GBRAIN_HOME is set by scripts/gbrain.sh.
#
# No embedding provider by design: keyword search works offline, and turning on
# embeddings later is an explicit, costed step (`docs/gbrain-integration.md`).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
brain="${GAXIS_GBRAIN_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/gaxis/gbrain}"

if [ -f "$brain/.gbrain/config.json" ] || [ -d "$brain/.gbrain" ]; then
  echo "==> gbrain brain already initialized at $brain (delete it to start over)"
else
  echo "==> initializing gbrain at $brain (PGLite, db-only, no embeddings)"
  "$repo_root/scripts/gbrain.sh" init --pglite --no-embedding --non-interactive \
    --db-only --path "$brain"
fi

bash "$repo_root/scripts/gbrain_doctor.sh" >/dev/null 2>&1 && echo "==> doctor: OK" || {
  echo "error: gbrain doctor reported a problem" >&2
  echo "run: pixi run gbrain-doctor" >&2
  exit 1
}
