#!/usr/bin/env python3
"""check-rates — verify dom's OpenRouter aliases + rate table against the live catalog.

Two checks (found necessary 2026-07-10, when 4 of 5 paid alias targets turned
out not to exist — dots-vs-dashes — and the opus rate was 3x stale):

  1. Every _OPENROUTER_ALIASES target in agent_tools.py EXISTS on OpenRouter.
  2. Every _OPENROUTER_RATES entry is within 2x of the live catalog price.

Run it ad hoc or from the weekly report cron (Phase 4). Requires network;
exits 2 (not 1) when the catalog is unreachable so cron can tell "stale
config" from "no internet".

Usage: check-rates.py [--agent-tools PATH]
"""

import argparse
import ast
import json
import re
import sys
import urllib.request
from pathlib import Path

CATALOG_URL = "https://openrouter.ai/api/v1/models"


def _find_agent_tools(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    # repo root = 4 levels up from this script (.github/skills/dom-usage/scripts/)
    root = Path(__file__).resolve().parents[4]
    for cand in root.rglob("agent_tools.py"):
        # Relative to root — the root itself may live under a filtered dir
        # name (e.g. .claude/worktrees/<agent>/); only prune descent dirs.
        parts = set(cand.relative_to(root).parts)
        if not parts & {".git", ".venv", "venv", "node_modules", ".claude"}:
            return cand
    raise SystemExit(f"agent_tools.py not found under {root} (use --agent-tools)")


def _extract_dict(source: str, name: str) -> dict:
    """Pull a top-level dict literal (values may be strings or tuples) out of the module source."""
    m = re.search(rf"^{name}[^=]*=\s*{{", source, re.MULTILINE)
    if not m:
        raise SystemExit(f"{name} not found in agent_tools.py")
    start = source.index("{", m.start())
    depth, i = 0, start
    while i < len(source):
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        if depth == 0:
            break
        i += 1
    return ast.literal_eval(source[start : i + 1])


def main() -> int:
    ap = argparse.ArgumentParser(description="verify OpenRouter aliases + rates against live catalog")
    ap.add_argument("--agent-tools", help="path to agent_tools.py (default: autodetect)")
    args = ap.parse_args()

    at_path = _find_agent_tools(args.agent_tools)
    src = at_path.read_text(encoding="utf-8")
    aliases = _extract_dict(src, "_OPENROUTER_ALIASES")
    rates = _extract_dict(src, "_OPENROUTER_RATES")

    try:
        with urllib.request.urlopen(CATALOG_URL, timeout=20) as resp:
            catalog = {m["id"]: m for m in json.loads(resp.read())["data"]}
    except Exception as e:
        print(f"⚠ cannot reach OpenRouter catalog ({e}) — currency unknown, not failing")
        return 2

    print("=" * 64)
    print(f"check-rates — {at_path}")
    print("=" * 64)
    issues = 0

    # 1) every alias target exists
    for alias, target in sorted(aliases.items()):
        if target in catalog:
            print(f"  ✓ alias {alias:<14} → {target}")
        else:
            issues += 1
            print(f"  ✗ alias {alias:<14} → {target}  DOES NOT EXIST on OpenRouter")

    # 2) every rate within 2x of live price for the models we actually route to
    print("-" * 64)
    for key, (r_in, r_out) in rates.items():
        live = next((catalog[t] for t in aliases.values() if key in t and t in catalog), None)
        if live is None:
            print(f"  · rate '{key}' — no routed model matches; skipped")
            continue
        p = live.get("pricing", {})
        l_in, l_out = float(p.get("prompt", 0)) * 1e6, float(p.get("completion", 0)) * 1e6
        ok = all(x / y <= 2 and y / x <= 2 for x, y in ((r_in, l_in), (r_out, l_out)) if y > 0)
        if ok:
            print(f"  ✓ rate  {key:<22} table ${r_in}/{r_out}  live ${l_in:g}/{l_out:g}")
        else:
            issues += 1
            print(f"  ✗ rate  {key:<22} table ${r_in}/{r_out}  live ${l_in:g}/{l_out:g}  (>2x off)")

    print("=" * 64)
    if issues:
        print(f"FAILED: {issues} stale alias/rate entr(y/ies) — update agent_tools.py + usage.py mirror")
        return 1
    print("PASSED: all alias targets exist; rates within 2x of live catalog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
