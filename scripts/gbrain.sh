#!/usr/bin/env bash
# Run gbrain with project-local state.
#
# Keeps gbrain's brain out of the user's home (nothing is written to ~/.gbrain),
# so gaxis can be tested, wiped and reinstalled without touching personal data:
#
#   GAXIS_GBRAIN_HOME  brain home (default: ${XDG_DATA_HOME:-~/.local/share}/gaxis/gbrain)
#   GAXIS_GBRAIN_SRC   source checkout (default: <repo>/vendor/gbrain)
#
# Usage:
#   pixi run gbrain --version
#   pixi run gbrain init --pglite
#   pixi run gbrain -- doctor
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src_dir="${GAXIS_GBRAIN_SRC:-$repo_root/vendor/gbrain}"
# Outside the git worktree on purpose: gbrain refuses to own a content directory
# inside a repository, and a brain next to source is one `git add -f` away from
# being committed. XDG data dir keeps it per-user and backup-friendly.
export GBRAIN_HOME="${GAXIS_GBRAIN_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/gaxis/gbrain}"
mkdir -p "$GBRAIN_HOME"

if [ ! -f "$src_dir/src/cli.ts" ]; then
  echo "error: gbrain is not installed — run 'pixi run gbrain-install'" >&2
  exit 1
fi

# Prefer the pinned bun vendored by install_gbrain.sh (gbrain needs a newer bun
# than conda-forge currently ships), fall back to the environment's bun.
if [ -x "$repo_root/vendor/bun/bin/bun" ]; then
  bun_bin="$repo_root/vendor/bun/bin/bun"
else
  bun_bin="$(command -v bun || true)"
fi
[ -n "$bun_bin" ] || { echo "error: bun not found — run 'pixi run gbrain-install'" >&2; exit 1; }

exec "$bun_bin" run "$src_dir/src/cli.ts" "$@"
