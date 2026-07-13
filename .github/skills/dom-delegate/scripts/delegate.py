#!/usr/bin/env python3
"""dom delegate — @dom's task-delegation engine.

@dom is a planner/governor: it NEVER implements. It delegates by writing
structured tasks into each subordinate bot's TODO.md (repo root) or memory.
The owning bot reads its tasks (`dom intake`), implements them, checks them
off, and commits. This script is the write/read machinery.

Registry: .github/dom-bots.json (bot -> dir/todo/memory/owner).
Bot repos resolve under the workspace root: $DOM_WORKSPACE, else the dom
repo's parent directory.

Commands:
  delegate.py bots
  delegate.py add <bot> "task text" [--priority P1|P2|P3] [--verify "cmd"]
                                    [--memory] [--tag NAME]
  delegate.py list [<bot>]          # open + done counts across bots
  delegate.py intake <bot>          # bot-side: print MY open @dom tasks

Task line format (machine-parseable, human-readable):
  - [ ] `DOM-20260710-1` **(P1)** <text>
        ↳ verify: `<cmd>`
        ↳ set by @dom 2026-07-10
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SECTION = "## 📋 @dom delegated tasks"
BLURB = (
    "<!-- Managed by `dom delegate`. @dom writes these; this bot implements, "
    "checks them off, and commits. `dom intake` lists your open ones. -->"
)


def _dom_root() -> Path:
    """Walk up from this script to the dom repo root (holds .github/dom-bots.json)."""
    p = Path(__file__).resolve()
    for cand in [p, *p.parents]:
        if (cand / ".github" / "dom-bots.json").exists():
            return cand
    # Fallback: assume <root>/.github/skills/dom-delegate/scripts/delegate.py
    return p.parents[4]


def _load_registry(root: Path) -> dict:
    reg = json.loads((root / ".github" / "dom-bots.json").read_text(encoding="utf-8"))
    import os
    ws_env = os.environ.get("DOM_WORKSPACE")
    workspace = Path(ws_env).expanduser() if ws_env else (root / reg.get("workspace_default", "..")).resolve()
    reg["_workspace"] = workspace
    return reg


def _bot(reg: dict, name: str) -> dict:
    bots = reg.get("bots", {})
    if name not in bots:
        raise SystemExit(f"unknown bot '{name}'. Known: {', '.join(sorted(bots))}")
    return bots[name]


def _target_file(reg: dict, bot: dict, use_memory: bool) -> Path:
    base = reg["_workspace"] / bot["dir"]
    rel = bot.get("memory") if use_memory else bot.get("todo")
    if use_memory and not rel:
        raise SystemExit(f"bot has no memory file; drop --memory to use {bot.get('todo')}")
    return base / rel


def _git(repo: Path, *args: str) -> str | None:
    """Run a read-only git command in `repo`; return stripped stdout or None on any failure."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _assert_target_fresh(path: Path) -> None:
    """Refuse to write if the bot repo is a stale checkout (behind its upstream).

    delegate is a faithful read-modify-write of the working tree: if that tree is
    behind origin (e.g. a subagent worktree branched off a pre-prune main and left
    the checkout stale), delegate would persist the OLD file + the new task, which
    reads as "delegate reverted my TODO". It never clobbers — it just writes back
    whatever it read. Abort here so the stale content can't be resurrected.
    No-op when the target isn't a git repo or has no upstream (nothing to compare).
    """
    repo = _git(path.parent, "rev-parse", "--show-toplevel")
    if repo is None:
        return  # not a git working tree — nothing to guard
    if _git(Path(repo), "rev-parse", "--abbrev-ref", "@{u}") is None:
        return  # no upstream configured — can't judge staleness
    behind = _git(Path(repo), "rev-list", "--count", "HEAD..@{u}")
    if behind and behind.isdigit() and int(behind) > 0:
        raise SystemExit(
            f"refusing to write {path.name}: {repo} is {behind} commit(s) behind its "
            f"upstream — a stale checkout. Sync it first (git -C {repo} pull --ff-only), "
            f"then re-run so the task appends to the current file (not a resurrected one)."
        )


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _next_id(text: str, day: str) -> str:
    prefix = f"DOM-{day}-"
    n = sum(1 for line in text.splitlines() if prefix in line) + 1
    return f"{prefix}{n}"


def _insert_task(content: str, task_block: str) -> str:
    lines = content.splitlines()
    # find managed section
    hdr = next((i for i, ln in enumerate(lines) if ln.strip() == SECTION), None)
    if hdr is None:
        sep = "" if content.endswith("\n\n") or not content else "\n"
        tail = "" if content.endswith("\n") else "\n"
        return f"{content}{tail}{sep}\n{SECTION}\n\n{BLURB}\n\n{task_block}\n"
    # find end of section (next '## ' header or EOF)
    end = len(lines)
    for i in range(hdr + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    # trim trailing blanks inside the section, then append the task
    j = end
    while j > hdr + 1 and lines[j - 1].strip() == "":
        j -= 1
    new = lines[:j] + [task_block] + lines[j:end] + lines[end:]
    return "\n".join(new) + ("\n" if content.endswith("\n") else "")


def cmd_add(reg: dict, args) -> int:
    bot = _bot(reg, args.bot)
    path = _target_file(reg, bot, args.memory)
    if not path.parent.exists():
        raise SystemExit(f"bot repo not found: {path.parent} (set $DOM_WORKSPACE?)")
    _assert_target_fresh(path)
    content = path.read_text(encoding="utf-8") if path.exists() else f"# {args.bot} TODO\n"
    tid = _next_id(content, _today())
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    block = f"- [ ] `{tid}` **({args.priority})** {args.text}"
    if args.tag:
        block += f"  _[{args.tag}]_"
    extra = [f"      ↳ verify: `{args.verify}`"] if args.verify else []
    extra.append(f"      ↳ set by @dom {day} (owner {bot.get('owner', '?')})")
    block = "\n".join([block, *extra])
    path.write_text(_insert_task(content, block), encoding="utf-8")
    dest = "memory" if args.memory else "TODO.md"
    print(f"✓ delegated {tid} ({args.priority}) → {args.bot} [{dest}]")
    print(f"  {args.text}")
    print(f"  file: {path}")
    return 0


def _scan(path: Path) -> tuple[int, int, list[str]]:
    """Return (open, done, open_task_lines) for a file's managed section."""
    if not path.exists():
        return 0, 0, []
    opn = dn = 0
    open_lines: list[str] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if s.startswith("- [ ] `DOM-"):
            opn += 1
            open_lines.append(s[6:])  # strip "- [ ] "
        elif s.startswith("- [x] `DOM-") or s.startswith("- [X] `DOM-"):
            dn += 1
    return opn, dn, open_lines


def cmd_list(reg: dict, args) -> int:
    names = [args.bot] if getattr(args, "bot", None) else list(reg["bots"])
    print(f"@dom delegated tasks  (workspace: {reg['_workspace']})")
    print("─" * 60)
    tot_o = tot_d = 0
    for name in names:
        bot = reg["bots"][name]
        o1, d1, _ = _scan(reg["_workspace"] / bot["dir"] / bot["todo"])
        o2 = d2 = 0
        if bot.get("memory"):
            o2, d2, _ = _scan(reg["_workspace"] / bot["dir"] / bot["memory"])
        o, d = o1 + o2, d1 + d2
        tot_o += o
        tot_d += d
        flag = "" if (o or d) else "  (none)"
        print(f"  {name:<20} open {o:>2}  done {d:>2}   {bot.get('status','')}{flag}")
    print("─" * 60)
    print(f"  {'TOTAL':<20} open {tot_o:>2}  done {tot_d:>2}")
    return 0


def cmd_intake(reg: dict, args) -> int:
    bot = _bot(reg, args.bot)
    print(f"@dom tasks for {args.bot} ({bot.get('owner','?')}) — implement highest priority first")
    print("─" * 60)
    found = False
    for rel, label in [(bot.get("todo"), "TODO.md"), (bot.get("memory"), "memory")]:
        if not rel:
            continue
        _, _, open_lines = _scan(reg["_workspace"] / bot["dir"] / rel)
        for ln in open_lines:
            found = True
            print(f"  [{label}] {ln}")
    if not found:
        print("  (no open @dom tasks — nothing delegated, or all done)")
    print("─" * 60)
    print("  When done: check the box (- [x]), commit, then `dom usage` if telemetry-related.")
    return 0


def cmd_bots(reg: dict, args) -> int:
    print(f"@dom bot roster  (workspace: {reg['_workspace']})")
    print("─" * 60)
    for name, b in reg["bots"].items():
        print(f"  {name:<20} {b.get('owner',''):<14} {b['dir']:<24} {b.get('status','')}")
    if reg.get("retired"):
        print("  retired:", ", ".join(reg["retired"]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="@dom task delegation via bot TODO.md / memory")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="delegate a task to a bot")
    a.add_argument("bot")
    a.add_argument("text")
    a.add_argument("--priority", default="P2", choices=["P1", "P2", "P3"])
    a.add_argument("--verify", default="", help="acceptance/verify command")
    a.add_argument("--tag", default="", help="optional short tag")
    a.add_argument("--memory", action="store_true", help="write to the bot's memory instead of TODO.md")

    lp = sub.add_parser("list", help="open/done counts across bots")
    lp.add_argument("bot", nargs="?")

    ip = sub.add_parser("intake", help="print a bot's open @dom tasks (bot-side)")
    ip.add_argument("bot")

    sub.add_parser("bots", help="print the bot roster")

    args = ap.parse_args()
    root = _dom_root()
    reg = _load_registry(root)
    return {"add": cmd_add, "list": cmd_list, "intake": cmd_intake, "bots": cmd_bots}[args.cmd](reg, args)


if __name__ == "__main__":
    sys.exit(main())
