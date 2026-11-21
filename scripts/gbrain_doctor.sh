#!/usr/bin/env bash
# Doctor wrapper: treats `sync_freshness` on write-through sources as expected.
#
# gaxis ingests pages with `put` (revision-guarded), never with `sync` — gbrain's
# sync requires git/writer-coordinator ownership of a canonical worktree, which a
# project checkout cannot give it. Other FAILs still fail the command.
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +e
out="$("$repo_root/scripts/gbrain.sh" doctor 2>&1)"
status=$?
set -e
echo "$out"

unexpected="$(printf '%s\n' "$out" | grep -E '^\s*\[FAIL\]' | grep -v 'sync_freshness')"
if [ -n "$unexpected" ]; then
  echo
  echo "unexpected failing checks:" >&2
  echo "$unexpected" >&2
  exit 1
fi
if [ "$status" -ne 0 ] && ! printf '%s\n' "$out" | grep -q 'Overall health'; then
  exit "$status"
fi
echo
echo "doctor: OK (sync_freshness excluded: write-through ingestion by design)"
