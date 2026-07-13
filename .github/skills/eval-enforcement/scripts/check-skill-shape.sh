#!/usr/bin/env bash
# Run the universal skill-shape eval against the current repo.
# Exits 0 on pass, 1 on fail. Skips cleanly if no skills exist.
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
exec python3 "$REPO_ROOT/.github/evals/skills/test_skill_shape.py"
