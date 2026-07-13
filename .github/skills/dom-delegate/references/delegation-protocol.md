# @dom delegation protocol

How @dom turns a cross-repo program into per-bot tasks, and how those tasks
move from assigned → done. @dom plans; bots implement.

## Task lifecycle

```
@dom decomposes → dom delegate → task lands in bot's TODO.md/memory (- [ ])
        ↓
bot runs `dom intake <self>` → implements highest-priority open task
        ↓
bot verifies (the task's `verify:` line) → checks box (- [x]) → commits
        ↓
@dom runs `dom tasks` → sees done count rise → updates the master plan
```

States are encoded in the checkbox:
- `- [ ]` open (not started / in progress)
- `- [x]` done (implemented + verified + committed by the bot)

Keep it to two states. If you need "in progress," append `_[wip]_` to the
line — but don't build a status machine; the point is lightweight delegation.

## The task schema (what a good task looks like)

```
- [ ] `DOM-20260710-1` **(P1)** <imperative, single outcome>
      ↳ verify: `<command or observable that proves it's done>`
      ↳ set by @dom <date> (owner <@bot>)
```

Rules for a well-formed task:
1. **One outcome.** If it has an "and," it's probably two tasks.
2. **Names the file/area** when known ("in src/mcp/tools/agent_tools.py …").
3. **Has a verify line** — a command (`dom usage`, `pytest …`) or an
   observable ("`.dom/usage.jsonl` gains a row"). No verify = under-specified.
4. **Priority reflects order, not importance** — P1 = do before P2.
5. **Self-contained** — the bot shouldn't need @dom's chat context to act.

## How @dom decomposes a program (prompt @dom follows)

> Given a cross-repo goal, for EACH affected bot produce the smallest set of
> self-contained tasks that bot can implement alone. For each task write:
> the one outcome, the file/area, and how to verify it. Respect each bot's
> constraints from recon (e.g. smartballz = MERGE not reinstall; clean repos =
> safe reinstall). Emit `dom delegate <bot> "…" --priority Pn --verify "…"`
> lines. Do NOT write code — only tasks. Prefer TODO.md for sprint work,
> `--memory` for standing policy the bot must carry across sessions.

Worked example (the token-economy rollout):
```bash
dom delegate smartballz "MERGE dom telemetry into src/mcp/tools/agent_tools.py, preserving deploy_status + src.mcp import" --priority P1 --verify "sbz still runs; dom usage renders; .dom/usage.jsonl grows"
dom delegate job    "Reinstall dom (~/workspace/dom/install.sh) to gain telemetry + dom cmd + dom-usage" --priority P1 --verify "dom usage renders after an sbz call"
dom delegate grof2  "Reinstall dom to gain telemetry" --priority P1 --verify "dom usage renders"
dom delegate nyx    "Reinstall dom to gain telemetry" --priority P1 --verify "dom usage renders"
```

## TODO.md vs memory — which target
- **TODO.md** (default): concrete, this-sprint work with a done state.
- **`--memory`**: a standing directive the bot must remember every session
  (policy, a convention, "always route SIMPLE work to Ollama"). Memory tasks
  are rarely "done" — they're rules. Use sparingly.

## What @dom does NOT do
No source edits, no `install.sh` runs in a bot repo, no code commits, no PRs.
If a task needs code, that's the bot's job — @dom's output is the task itself.
(An operator/human may run @dom's engine to implement on @dom's behalf; the
persona-level contract is that @dom-as-planner stays out of implementation.)
