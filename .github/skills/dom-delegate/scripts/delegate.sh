#!/usr/bin/env bash
# delegate.sh — thin wrapper around delegate.py (@dom's task-delegation engine).
#
#   dom delegate <bot> "task"  [--priority P1] [--verify "cmd"] [--memory] [--tag X]
#   dom tasks [<bot>]          # open/done counts (calls: list)
#   dom intake <bot>           # a bot's own open @dom tasks
#   dom bots                   # roster
#
# @dom writes tasks into each bot's TODO.md / memory; bots implement. Pure
# stdlib Python; safe to run from the dom repo or any installed consumer.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/delegate.py" "$@"
