#!/usr/bin/env bash
# Local lint gate — mirrors the CI `lint` job in .github/workflows/ci.yml
# VERBATIM so a green run here means a green run there. CI runs BOTH `ruff
# check` (lint rules) AND `ruff format --check` (formatting) — running only the
# former locally is how a formatter-only failure slips past into CI.
#
# Usage:
#   scripts/lint.sh          # check only (what CI does); non-zero exit on drift
#   scripts/lint.sh --fix    # auto-apply: `ruff check --fix` + `ruff format`
#
# Ruff is pinned to the CI version below; if a local ruff differs it is only a
# warning (behaviour can drift between ruff releases, so prefer a match).
set -euo pipefail

# Resolve this script's real location (following symlinks) so the `cd` to the
# repo root is correct however it's invoked — by relative path, via a symlink,
# or `source`d. Trusting $0 breaks under all three; BASH_SOURCE + a readlink
# loop is the portable idiom (works without GNU `readlink -f`).
src="${BASH_SOURCE[0]}"
while [[ -h "$src" ]]; do
  dir="$(cd -P "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  [[ "$src" != /* ]] && src="$dir/$src"
done
cd "$(cd -P "$(dirname "$src")/.." && pwd)"

RUFF_PIN="0.15.20"
PATHS=(src/ tests/)

# Prefer the project venv's ruff, else whatever's on PATH.
if [[ -x .venv/bin/ruff ]]; then
  RUFF=".venv/bin/ruff"
else
  RUFF="ruff"
fi

# Fail with guidance, not a raw "command not found", if ruff is missing.
if ! command -v "$RUFF" >/dev/null 2>&1; then
  echo "error: ruff not found (looked for .venv/bin/ruff, then PATH)." >&2
  echo "       install it: pip install ruff==$RUFF_PIN" >&2
  exit 1
fi

have_ver="$("$RUFF" --version 2>/dev/null | awk '{print $2}')" || true
if [[ -n "$have_ver" && "$have_ver" != "$RUFF_PIN" ]]; then
  echo "warning: ruff $have_ver differs from CI pin $RUFF_PIN (pip install ruff==$RUFF_PIN)" >&2
fi

if [[ "${1:-}" == "--fix" ]]; then
  # Mutating: fix lint findings, then reformat. Re-run without --fix to verify.
  "$RUFF" check --fix "${PATHS[@]}"
  "$RUFF" format "${PATHS[@]}"
  echo "applied fixes — re-run 'scripts/lint.sh' to confirm the gate is green"
else
  # Non-mutating, exactly as CI runs it (order and paths identical).
  "$RUFF" check "${PATHS[@]}"
  "$RUFF" format --check "${PATHS[@]}"
  echo "lint gate passed (matches CI)"
fi
