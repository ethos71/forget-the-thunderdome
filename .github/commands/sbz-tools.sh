#!/usr/bin/env bash
# sbz-tools.sh — DEPRECATED shim (removed next release).
#
# The `sbz` name is gone: the toolkit surface is now the `dom` umbrella command,
# invoked as `@dom --<command>`:
#   sbz <file> 'change' 'test'   →  dom task <file> 'change' 'test'
#   sbz-status                   →  dom status
#   sbz-pull                     →  dom pull
#   ask 'question'               →  dom ask 'question'
#
# This shim sources the real implementation (dom-tools.sh) and keeps the old
# bare `sbz*` names working for one release so existing ~/.bashrc lines and
# muscle memory don't break mid-migration. Update your ~/.bashrc to:
#   source <repo>/.github/commands/dom-tools.sh
# (or better: just use `dom <command>` — no sourcing needed).

_SBZ_SHIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
set +u; source "$_SBZ_SHIM_DIR/dom-tools.sh"; set -u

_sbz_deprecated() { echo "⚠️  '$1' is deprecated → use '$2' (the sbz name is going away)." >&2; }

sbz()        { _sbz_deprecated "sbz"        "dom task";   _dom_task   "$@"; }
sbz-pull()   { _sbz_deprecated "sbz-pull"   "dom pull";   _dom_pull   "$@"; }
sbz-status() { _sbz_deprecated "sbz-status" "dom status"; _dom_status "$@"; }

export -f sbz sbz-pull sbz-status 2>/dev/null || true
