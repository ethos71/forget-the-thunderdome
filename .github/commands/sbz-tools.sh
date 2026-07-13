#!/usr/bin/env bash
# sbz-tools.sh — dom AI team shell helpers
#
# Source this file to get all AI team shortcuts in your shell:
#   source /home/dominick/workspace/forget-the-thunderdome/.github/commands/sbz-tools.sh
#
# Add to ~/.bashrc for permanent setup:
#   echo 'source /home/dominick/workspace/forget-the-thunderdome/.github/commands/sbz-tools.sh' >> ~/.bashrc

SBZ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ask — local Ollama Q&A (free, private)
ask() {
  "$SBZ_DIR/ask" "$@"
}

# route — which AI tool should handle this task?
route() {
  "$SBZ_DIR/route-task.sh" "$@"
}

# gemini — ask Gemini about the codebase (API-powered, 1M context).
# OPTIONAL: dom does not ship the gemini wrapper; repos that have one
# (e.g. smartballz) get the real command, everyone else gets a hint.
gemini() {
  if [[ -x "$SBZ_DIR/gemini" ]]; then
    poetry --directory /home/dominick/workspace/forget-the-thunderdome run "$SBZ_DIR/gemini" "$@"
  else
    echo "gemini: not installed in this repo (optional — dom doesn't ship it)."
    echo "  Free large-codebase reads: paste files into https://aistudio.google.com"
  fi
}

# sbz — delegate an atomic task with auto-routing
# model="auto" (default): classifies complexity through the four-tier waterfall
#   SIMPLE→ollama, MEDIUM→haiku, COMPLEX→sonnet, ARCHITECTURAL→opus
# Usage: sbz <file> <change_description> [test_command] [model]
# Models: auto (default), ollama (force free), haiku (~$0.01), sonnet (~$0.10), opus (~$2.00)
# Example: sbz src/api/auth.py "Fix error message" "poetry run pytest test/"
sbz() {
  local file="${1:-}"
  local change="${2:-}"
  local test="${3:-echo 'no test'}"
  local model="${4:-auto}"
  local sbz_py

  if [[ -z "$file" || -z "$change" ]]; then
    echo "Usage: dom task <file> <change_description> [test_command] [model=auto]"
    echo "       dom task src/api/auth.py 'Fix error message' 'poetry run pytest'"
    echo ""
    echo "Models: auto (routes by complexity), ollama (free/local), haiku (~\$0.01), sonnet (~\$0.10), opus (~\$2.00)"
    return 1
  fi

  # Local models can run 1-3+ min/call; a short foreground shell timeout will
  # kill the delegation mid-generation (the abort IS logged to .dom/usage.jsonl).
  echo "⏳ sbz: local-model calls can take minutes — avoid short shell timeouts."

  sbz_py=$(cat <<PYEOF
import sys
sys.path.insert(0, '/home/dominick/workspace/forget-the-thunderdome/.github/mcp')
sys.path.insert(0, '/home/dominick/workspace/forget-the-thunderdome')
from tools.agent_tools import delegate_task
result = delegate_task(
    files=["$file"],
    change="""$change""",
    test="""$test""",
    model="$model",
)
import json
print(json.dumps(result, indent=2))
PYEOF
)

  # Use the project's poetry env only when it's actually USABLE — a
  # pyproject.toml of bare tool-configs (no [project]/[tool.poetry] name)
  # makes poetry error out (seen in Grof-2). Plain python3 otherwise
  # (agent_tools needs only stdlib + openai).
  if command -v poetry &>/dev/null \
     && poetry --directory /home/dominick/workspace/forget-the-thunderdome env info -p &>/dev/null; then
    poetry --directory /home/dominick/workspace/forget-the-thunderdome run python -c "$sbz_py"
  else
    python3 -c "$sbz_py"
  fi
}

# sbz-pull — pull the recommended code model for Ollama
sbz-pull() {
  echo "Pulling qwen2.5-coder:7b (recommended for code tasks)..."
  ollama pull qwen2.5-coder:7b
  echo ""
  echo "Also useful:"
  echo "  ollama pull llama3.1:8b     (general Q&A, already used by 'ask')"
  echo "  ollama pull codellama:7b    (alternative code model)"
  echo "  ollama pull deepseek-coder:6.7b  (strong on Python/SQL)"
}

# sbz-status — show AI team readiness
sbz-status() {
  echo ""
  echo "dom AI team Status"
  echo "─────────────────────────"

  # Ollama
  if command -v ollama &>/dev/null; then
    local model
    model=$(ollama list 2>/dev/null | grep -v "^NAME" | awk '{print $1}' | head -1)
    echo "  ✅ Ollama       → llama3.1:8b ready  (ask 'question')"
  else
    echo "  ❌ Ollama       → not installed"
    echo "     Fix: curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.1:8b"
  fi

  # route-task.sh
  if [[ -x "$SBZ_DIR/route-task.sh" ]]; then
    echo "  ✅ route-task   → ready              (route [task-type])"
  else
    echo "  ❌ route-task   → missing"
  fi

  # gemini-bundle — optional, not shipped by dom; only flag repos that have it
  if [[ -x "$SBZ_DIR/gemini-bundle" ]]; then
    echo "  ✅ gemini       → ready              (gemini --db | --auth | --api | --react)"
  else
    echo "  💡 gemini       → optional, not installed (large reads: aistudio.google.com)"
  fi

  # Perplexity (can only check if it's bookmarked / accessible)
  echo "  🌐 Perplexity   → perplexity.ai       (free web search, no tokens)"

  # @sbz — Ollama (free) or OpenRouter fallback
  if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    local models
    models=$(ollama list 2>/dev/null | grep -c "qwen2.5-coder" || true)
    if [[ "$models" -gt 0 ]]; then
      echo "  ✅ @sbz         → qwen2.5-coder (Ollama, FREE)  (sbz <file> <change>)"
    else
      echo "  ⚠️  @sbz         → Ollama running but qwen2.5-coder not installed"
      echo "     Fix: sbz-pull"
    fi
  else
    local sbz_key
    sbz_key=$(grep OPENROUTER_API_KEY /home/dominick/workspace/forget-the-thunderdome/.env 2>/dev/null | cut -d= -f2-)
    if [[ -n "$sbz_key" ]]; then
      echo "  ⚠️  @sbz         → Ollama offline, fallback: Haiku via OpenRouter"
      echo "     Tip: ollama serve  (to enable free local)"
    else
      echo "  ❌ @sbz         → Ollama offline + no OPENROUTER_API_KEY"
    fi
  fi

  # Copilot
  if command -v gh &>/dev/null; then
    echo "  ✅ GitHub CLI   → ready              (Copilot: gh copilot suggest)"
  fi
  echo "  💡 Copilot Chat → VS Code sidebar    (Ctrl+Shift+I)"
  echo "  💡 Claude.ai    → claude.ai/projects  (design mockups, separate quota)"
  echo ""
  echo "  Quick routing:  route          (interactive)"
  echo "  Quick Q&A:      ask 'question' (Ollama, free)"
  echo "  Atomic task:    sbz <file> 'change' (Haiku, cheap)"
  echo "  Codebase read:  gemini > /tmp/bundle.txt  (paste into aistudio.google.com)"
  echo ""
}

export -f ask route gemini sbz sbz-pull sbz-status 2>/dev/null || true
