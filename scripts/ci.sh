#!/usr/bin/env bash
# Local CI gate — a fast pre-push check that mirrors the GitHub `ci.yml` jobs.
#
# GitHub Actions runs the authoritative gate on every push/PR (this is a public
# repo, so Actions is free), across the 3.11/3.12/3.13 matrix. This script runs
# the same checks against your local interpreter so you can catch failures
# before pushing. It mirrors the two CI jobs:
#   - lint: `ruff check` + `ruff format --check`  (via scripts/lint.sh, verbatim)
#   - test: `pytest tests/ -q`
#
# It uses the project venv if one exists (.venv/bin/python), else `python` on
# PATH. Set the venv up first with the kernel + tutor installed:
#   python -m venv .venv && . .venv/bin/activate
#   pip install "git+https://github.com/baggybin/salient-core-public.git"
#   pip install -e ".[dev]"
#
# Usage:
#   scripts/ci.sh          # lint (check-only) + tests; non-zero exit on failure
#   scripts/ci.sh --fix    # auto-apply lint fixes first, then run tests
set -euo pipefail

# Resolve this script's real location (following symlinks) so the cd to the repo
# root is correct however it's invoked. Same idiom as scripts/lint.sh.
src="${BASH_SOURCE[0]}"
while [[ -h "$src" ]]; do
  dir="$(cd -P "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  [[ "$src" != /* ]] && src="$dir/$src"
done
root="$(cd -P "$(dirname "$src")/.." && pwd)"
cd "$root"

# Prefer the project venv's python (it has the kernel installed), else PATH.
if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="python"
fi

echo "== lint =="
if [[ "${1:-}" == "--fix" ]]; then
  scripts/lint.sh --fix
  scripts/lint.sh              # re-verify the gate is clean after fixing
else
  scripts/lint.sh
fi

echo
echo "== test ($("$PY" --version 2>&1)) =="
"$PY" -m pytest tests/ -q

echo
echo "local CI gate passed (matches ci.yml jobs; CI also runs the full 3.11/3.12/3.13 matrix on push)"
