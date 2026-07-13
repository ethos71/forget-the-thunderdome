#!/usr/bin/env bash
# Run both universal evals plus any project-local evals under
# .github/evals/. Exits 0 only if everything passes or skips cleanly.
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$REPO_ROOT"

echo "── skill shape ─────────────────────────────────────────────"
python3 .github/evals/skills/test_skill_shape.py

echo ""
echo "── role shape ──────────────────────────────────────────────"
python3 .github/evals/skills/test_role_shape.py

echo ""
echo "── memory architecture ─────────────────────────────────────"
python3 .github/evals/skills/test_memory_architecture.py

echo ""
echo "── toolkit smoke (sbz import + eval freshness) ─────────────"
python3 .github/evals/skills/test_toolkit_smoke.py

echo ""
echo "── classifier calibration (skip-safe: needs local Ollama) ──"
if [[ -f .github/evals/ai/test_classifier_calibration.py ]]; then
  python3 .github/evals/ai/test_classifier_calibration.py
else
  echo "classifier-calibration eval not installed — skipping"
fi

echo ""
echo "── metered ask (skip-safe: needs local Ollama + openai) ────"
if [[ -f .github/evals/tools/test_ask_logged.py ]]; then
  python3 .github/evals/tools/test_ask_logged.py
else
  echo "metered-ask eval not installed — skipping"
fi

echo ""
echo "── usage audit — Ollama cost gate, last 30d ────────────────"
# Exits 1 if a SIMPLE task was billed to a paid model (dom usage contract).
# No .dom/usage.jsonl (e.g. fresh CI checkout) → renders empty and passes.
if [[ -x .github/skills/dom-usage/scripts/usage.sh ]]; then
  .github/skills/dom-usage/scripts/usage.sh --since 30
else
  echo "dom-usage skill not installed — skipping cost gate"
fi

if [[ -f .github/evals/run_all.py ]]; then
  echo ""
  echo "── project-local evals ─────────────────────────────────────"
  python3 .github/evals/run_all.py
fi
