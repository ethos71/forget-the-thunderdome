#!/usr/bin/env python3
"""Classifier calibration eval — the routing classifier must agree with the
labeled task→tier fixtures at ≥90%.

Rule pinned: docs/routing-guide.md four-tier waterfall + the DOM-6 shape rule
(2026-07-10 smartballz teach-back, dom TODO `DOM-20260710-6`): SIMPLE is ONE
single-line/single-hunk mechanical change; ANY multi-line prose/comment
restructure is MEDIUM even when conceptually trivial; single-file work is
never COMPLEX. A drifting classifier silently changes spend — SIMPLE→MEDIUM
overshoot costs ~10x, MEDIUM→SIMPLE undershoot ships failed local edits.

Oracle: the labeled fixtures below (real data — the labels ARE the routing
contract). Skip-safe: exits 0 with a ⚠️ message when local Ollama is not
reachable (e.g. CI), per eval-policy. Fix site on failure:
`_ROUTER_SYSTEM` in `.github/mcp/tools/agent_tools.py`.
"""

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GATE = 0.90

# (task description, files, expected tier)
FIXTURES = [
    # SIMPLE — one single-line/single-hunk mechanical change
    ("Rename variable x to y", ["src/api/auth.py"], "SIMPLE"),
    ("Fix typo 'recieve' to 'receive' in the error message", ["src/api/main.py"], "SIMPLE"),
    ("Update the DEFAULT_TIMEOUT constant from 30 to 60", ["src/config.py"], "SIMPLE"),
    ("Toggle the ENABLE_CACHE flag to False", ["src/settings.py"], "SIMPLE"),
    # MEDIUM — one file: real logic, or ANY multi-line prose restructure
    ("Rewrite this 10-line header comment block to describe the new deploy flow", ["src/scripts/deploy.sh"], "MEDIUM"),
    ("Restructure the module docstring into sections", ["src/models/predict.py"], "MEDIUM"),
    ("Add a retry helper function with exponential backoff", ["src/http/client.py"], "MEDIUM"),
    ("Write a unit test for the parse_date function", ["test/test_utils.py"], "MEDIUM"),
    ("Fix the off-by-one bug in the pagination loop", ["src/api/list.py"], "MEDIUM"),
    ("Add a --verbose flag to the CLI argument parser", ["src/cli.py"], "MEDIUM"),
    # COMPLEX — multiple files / subsystem behavior
    ("Refactor JWT handling across the auth module's 4 files", ["src/auth/jwt.py", "src/auth/middleware.py", "src/auth/session.py", "src/auth/refresh.py"], "COMPLEX"),
    ("Debug why the cache invalidation intermittently misses updates across the write path", ["src/cache/store.py", "src/cache/invalidate.py"], "COMPLEX"),
    ("Change error-response format across all API routes in the service", ["src/api/"], "COMPLEX"),
    # ARCHITECTURAL — cross-system design/migration
    ("Plan a database migration that spans the API, worker, and reporting subsystems", ["src/"], "ARCHITECTURAL"),
    ("Design a session-token migration plan across 4 services with backwards-compatible rollout", ["services/"], "ARCHITECTURAL"),
    ("Deep debug of a data-corruption issue requiring whole-codebase reasoning across ingest, storage, and serving", ["."], "ARCHITECTURAL"),
]


def _load_agent_tools():
    for cand in PROJECT_ROOT.rglob("agent_tools.py"):
        # Filter on the path RELATIVE to the repo root — the root itself may
        # legitimately live under a filtered dir name (e.g. Claude Code git
        # worktrees at <repo>/.claude/worktrees/<agent>/), which must not
        # make the eval self-skip.
        rel_parts = set(cand.relative_to(PROJECT_ROOT).parts)
        if not rel_parts & {".git", ".venv", "venv", "node_modules", ".claude"}:
            spec = importlib.util.spec_from_file_location("agent_tools_eval", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, cand
    return None, None


def main() -> int:
    mod, path = _load_agent_tools()
    if mod is None:
        print("⚠️  Skipping — agent_tools.py not found (toolkit not installed)")
        return 0

    running, _ = mod._ollama_status()
    if not running:
        print("⚠️  Skipping — local Ollama not reachable (classifier needs it); start `ollama serve`")
        return 0

    print("=" * 64)
    print(f"classifier-calibration eval — {len(FIXTURES)} labeled fixtures, gate ≥{GATE:.0%}")
    print("=" * 64)

    hits = 0
    misses: list[str] = []
    for change, files, want in FIXTURES:
        got, routed = mod._classify_task(change, files)
        ok = got == want
        hits += ok
        mark = "✓" if ok else "✗"
        line = f"  {mark} {want:<13} got {got:<13} {change[:52]!r}"
        print(line)
        if not ok:
            misses.append(line)

    score = hits / len(FIXTURES)
    print("=" * 64)
    print(f"agreement: {hits}/{len(FIXTURES)} = {score:.0%}  (gate {GATE:.0%})")
    if score < GATE:
        print("FAILED: classifier disagrees with the routing contract.")
        print(f"Fix site: _ROUTER_SYSTEM in {path}")
        print("Rule: docs/routing-guide.md tiers + DOM-6 shape rule (multi-line prose → MEDIUM).")
        return 1
    print("PASSED: classifier calibrated within gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
