---
name: dom-delegate
description: "@dom's task-delegation system. Use when @dom needs to hand work to a subordinate bot (@smartballz, @job, @grof2, @nyx, etc.) — it writes a structured task into that bot's root TODO.md or memory; the bot implements it. @dom NEVER implements. Also use bot-side to read your own delegated tasks (dom intake). Commands: dom delegate/tasks/intake/bots."
---

# dom-delegate

@dom is the boss/orchestrator and **never implements**. It delegates by
writing structured tasks into each subordinate bot's `TODO.md` (repo root) or
memory. The owning bot reads its tasks, implements them, checks them off, and
commits. This skill is the machinery + the protocol both sides follow.

## The two sides

**@dom side — hand out work:**
```bash
dom bots                                   # the roster (name → owner → dir → status)
dom delegate <bot> "task text" --priority P1 --verify "how to know it's done"
dom delegate <bot> "task" --memory         # write to the bot's memory instead of TODO.md
dom tasks [<bot>]                          # open/done counts across all bots
```

**Bot side — take work:**
```bash
dom intake <bot>     # print MY open @dom tasks, highest priority first
# implement → check the box (- [x]) → commit → `dom usage` if telemetry-related
```

## What gets written
A machine-parseable, human-readable checkbox under a managed
`## 📋 @dom delegated tasks` section in the target file:

```
- [ ] `DOM-20260710-1` **(P1)** Merge telemetry preserving deploy_status
      ↳ verify: `dom usage renders + .dom/usage.jsonl grows`
      ↳ set by @dom 2026-07-10 (owner @smartballz)
```

- IDs (`DOM-<date>-<n>`) auto-increment per file per day.
- `--priority` P1 (do first) / P2 (default) / P3.
- `--verify` states the acceptance check so the bot knows when it's done.
- Repeated `dom delegate` calls append into the **same** section (no dup headers).

## Registry
Bots live in `.github/dom-bots.json` (name → dir / todo / memory / owner /
layout / status). Bot repos resolve under the workspace root: `$DOM_WORKSPACE`,
else the dom repo's parent directory. Edit the JSON to add/retire a bot.

## Rules (the @dom contract)
- @dom writes TODO + memory ONLY. It does not edit source, run installs,
  commit code, or open PRs in a bot's repo. Discoveries become **tasks**.
- Every task carries a `--verify` (or an obvious acceptance) — a task the bot
  can't confirm done is under-specified.
- Choose the target: durable, this-sprint work → `TODO.md`; a standing
  directive / policy the bot must remember across sessions → `--memory`.
- Don't delegate to a `retired` bot (see registry).

See `references/delegation-protocol.md` for the task lifecycle and how @dom
decomposes a program into per-bot tasks, and `references/bot-intake.md` for
the exact instruction a bot follows when it picks up @dom tasks.
