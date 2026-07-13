#!/usr/bin/env bash
#
# route-task.sh — AI Team Task Router
#
# Route tasks to the cheapest capable tool.
# Saves money, improves code quality, avoids unnecessary API calls.
#
# Usage:
#   ./route-task.sh
#   (interactive mode asks questions)
#
# Or:
#   route-task.sh autocomplete
#   route-task.sh research
#   route-task.sh design
#   route-task.sh refactor
#   route-task.sh debug
#

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Print banner
print_banner() {
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BLUE}  dom AI team — Task Router${NC}"
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Print result
print_result() {
  local tool=$1
  local reason=$2
  local cost=$3

  echo
  echo -e "${GREEN}✅ RECOMMENDED: $tool${NC}"
  echo -e "   Reason: $reason"
  echo -e "   Cost: $cost"
  echo
}

print_details() {
  local tool=$1
  local usage=$2

  echo -e "${YELLOW}📖 How to use:${NC}"
  echo "   $usage"
  echo
}

print_link() {
  local tool=$1
  local link=$2

  echo -e "${YELLOW}🔗 Link:${NC}"
  echo "   $link"
  echo
}

# Task routing functions
route_autocomplete() {
  print_result "GitHub Copilot" "Fastest for code generation" "FREE (you have it)"
  print_details "Copilot" "Start typing → Tab to accept suggestion"
  echo -e "${BLUE}Examples:${NC}"
  echo "   • Add a new function (type signature, Copilot fills body)"
  echo "   • Write unit test (type test name, Copilot generates test body)"
  echo "   • Generate docstring (type ''', Copilot completes)"
}

route_research() {
  print_result "Perplexity" "Free web search, no tokens used" "FREE"
  print_details "Perplexity" "https://perplexity.ai → Ask question → Get citations"
  print_link "Perplexity" "https://perplexity.ai"
  echo -e "${BLUE}Examples:${NC}"
  echo "   • 'How does The Odds API work?'"
  echo "   • 'Best pattern for FastAPI + React auth'"
  echo "   • 'What's the current version of llama3.1?'"
}

route_design() {
  print_result "Claude.ai Projects" "Separate quota, visual artifacts" "SEPARATE QUOTA (no API token cost)"
  print_details "Claude.ai" "https://claude.ai/projects → Create project → Paste requirements → Get mockup"
  print_link "Claude.ai" "https://claude.ai/projects"
  echo -e "${BLUE}Examples:${NC}"
  echo "   • 'Design a React admin dashboard for fantasy baseball'"
  echo "   • 'Create wireframes for the new Sim Lab interface'"
  echo "   • 'Generate example JSON for our API responses'"
}

route_explanation() {
  print_result "Copilot Chat (VS Code)" "Code explanation in editor" "INCLUDED (no tokens)"
  print_details "Copilot Chat" "Cmd+Shift+I → Select code → Ask question"
  echo -e "${BLUE}Examples:${NC}"
  echo "   • 'Explain what this function does'"
  echo "   • 'How would you refactor this for readability?'"
  echo "   • 'What's wrong with this SQL query?'"
}

route_largeread() {
  print_result "Gemini 2.0 Flash" "1M tokens, free tier, codebase review" "FREE (1M tokens/day)"
  print_details "Gemini" "aistudio.google.com → Create project → Paste files → Ask questions"
  print_link "Gemini AI Studio" "https://aistudio.google.com"
  echo -e "${BLUE}Examples:${NC}"
  echo "   • 'Read auth.py + oauth.py. Explain the flow.'"
  echo "   • 'Find all places where fantasy_matchups is queried'"
  echo "   • 'Does this refactor break any existing endpoints?'"
}

route_quickqa() {
  print_result "Ollama (local)" "Private, free, ~5s response time" "FREE"
  print_details "Ollama" "ask 'Your question here' (or: ollama run llama3.1:8b 'question')"
  echo -e "${BLUE}Setup (one-time):${NC}"
  echo "   echo 'ask() { ollama run llama3.1:8b \"\$@\"; }' >> ~/.bashrc"
  echo "   source ~/.bashrc"
  echo
  echo -e "${BLUE}Examples:${NC}"
  echo "   • ask 'What does this regex do?'"
  echo "   • ask 'Generate 5 test cases for this function'"
  echo "   • ask 'Check this code for security issues'"
}

route_atomic() {
  print_result "dom task (auto-routed: Ollama → Haiku → Sonnet → Opus)" "Single-file tasks, atomic scope" "FREE if simple, ~\$0.01 if medium"
  print_details "dom task" "dom task <file> <change> [test] — auto-classifies complexity and picks cheapest model"
  echo -e "${BLUE}Examples:${NC}"
  echo "   dom task src/api/routes/auth.py 'Rename port to server_port' 'echo ok'"
  echo "   dom task src/react_app/src/pages/WaiversPage.tsx 'Add buy-low badge' 'npm run build --prefix src/react_app'"
  echo
  echo -e "${BLUE}How routing works (model=auto, four-tier waterfall):${NC}"
  echo "   SIMPLE        → Ollama/qwen   (free, local)  — rename, typo, constant change"
  echo "   MEDIUM        → Haiku         (~\$0.01)       — new function, small feature, test"
  echo "   COMPLEX       → Sonnet        (~\$0.10)       — multi-file refactor, single-subsystem change"
  echo "   ARCHITECTURAL → Opus          (~\$2.00)       — cross-system design, hard debug, deep planning"
  echo
  echo -e "${BLUE}Force a specific model:${NC}"
  echo "   dom task src/file.py 'change' 'test' ollama   # force free local"
  echo "   dom task src/file.py 'change' 'test' haiku    # force Haiku"
  echo "   dom task src/file.py 'change' 'test' sonnet   # force Sonnet"
  echo "   dom task src/file.py 'change' 'test' opus     # force Opus (most expensive)"
  echo
  echo -e "${BLUE}Preview routing without running:${NC}"
  echo "   Use sb_delegate_task(..., dry_run=True) in MCP"
}

route_complex() {
  print_result "@smartballz (Claude Sonnet)" "Multi-file refactor, single-subsystem change" "~\$0.10 per task"
  print_details "@smartballz" "Ask for clarification → Plan with verification → Implement"
  echo -e "${BLUE}Examples:${NC}"
  echo "   • 'Refactor authentication across 5 files in the auth subsystem'"
  echo "   • 'Add a new FastAPI route + matching React page'"
  echo "   • 'Debug a multi-file issue inside one module'"
}

route_architectural() {
  print_result "@smartballz orchestrator (Claude Opus)" "Cross-system design, hard debug, deep planning" "EXPENSIVE API (~\$2.00 per task)"
  print_details "@smartballz" "Use sparingly. Reserve for work no other tier can do."
  echo -e "${BLUE}Examples:${NC}"
  echo "   • 'Plan a database migration that spans 3 subsystems'"
  echo "   • 'Debug a flaky issue requiring whole-codebase reasoning'"
  echo "   • 'Design a new auth model with backwards-compatible rollout'"
}

# Interactive mode
interactive_mode() {
  print_banner

  echo
  echo -e "${YELLOW}What type of task is this?${NC}"
  echo "  1) Autocomplete code"
  echo "  2) Research (API docs, library comparison)"
  echo "  3) Design UI mockup"
  echo "  4) Explain existing code"
  echo "  5) Read 10+ files at once"
  echo "  6) Quick Q&A (simple question)"
  echo "  7) Single-file change (atomic scope)"
  echo "  8) Multi-file refactor (complex)"
  echo "  9) Cross-system architecture / hard debug (Opus)"
  echo "  0) Help / Exit"
  echo
  read -p "Choose (0-9): " choice

  case $choice in
    1) route_autocomplete ;;
    2) route_research ;;
    3) route_design ;;
    4) route_explanation ;;
    5) route_largeread ;;
    6) route_quickqa ;;
    7) route_atomic ;;
    8) route_complex ;;
    9) route_architectural ;;
    0)
      echo -e "${BLUE}See docs/routing-guide.md for full guide${NC}"
      exit 0
      ;;
    *)
      echo -e "${RED}Invalid choice${NC}"
      interactive_mode
      ;;
  esac

  echo
  read -p "Route another task? (y/n): " another
  if [[ $another == "y" || $another == "Y" ]]; then
    interactive_mode
  fi
}

# Direct mode (arguments)
direct_mode() {
  local task_type=$1

  case $task_type in
    autocomplete) route_autocomplete ;;
    research) route_research ;;
    design) route_design ;;
    explain) route_explanation ;;
    largeread|read) route_largeread ;;
    qa|quick) route_quickqa ;;
    atomic) route_atomic ;;
    complex|refactor) route_complex ;;
    architectural|architecture|opus|plan) route_architectural ;;
    help)
      echo "Usage: route-task.sh [task-type]"
      echo "Task types: autocomplete, research, design, explain, largeread, qa, atomic, complex, architectural, help"
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown task type: $task_type${NC}"
      echo "See: route-task.sh help"
      exit 1
      ;;
  esac
}

# Main
if [[ $# -eq 0 ]]; then
  interactive_mode
else
  print_banner
  direct_mode "$1"
fi
