#!/usr/bin/env bash
# Run the universal memory-architecture eval against the current repo.
# Exits 0 on pass, 1 on fail. Skips cleanly on fresh projects.
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
exec python3 "$REPO_ROOT/.github/evals/skills/test_memory_architecture.py"
