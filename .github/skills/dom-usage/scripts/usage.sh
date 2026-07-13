#!/usr/bin/env bash
# usage.sh — dom /usage entry point.
#
# Prints tokens-per-model and an Ollama-enforcement audit from the log that
# delegate_task writes (.dom/usage.jsonl by default). Pure stdlib Python — no
# deps, safe to run anywhere the delegation log lives.
#
#   scripts/usage.sh                 # full report, all time
#   scripts/usage.sh --since 7       # last 7 days only
#   scripts/usage.sh --json          # machine-readable aggregates
#   scripts/usage.sh --log path.jsonl
#
# Exit code: 0 on a clean audit, 1 when hard enforcement violations exist
# (a free-tier task was billed to a paid model) — so CI can gate on it.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/usage.py" "$@"
