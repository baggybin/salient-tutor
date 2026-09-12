#!/usr/bin/env bash
# Enable this repo's tracked git hooks (the pre-push clean-checkout gate).
# Run once per clone. core.hooksPath is local config, so it is not carried by
# the checkout itself — this one command points git at the tracked .githooks/.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
echo "core.hooksPath -> .githooks  (pre-push clean-checkout gate is now active)"
