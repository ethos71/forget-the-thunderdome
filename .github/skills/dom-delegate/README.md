# dom-delegate skill

@dom's task-delegation system: @dom writes structured tasks into each
subordinate bot's `TODO.md` / memory; the bot implements them. @dom never
implements.

See [`SKILL.md`](./SKILL.md) for commands and rules,
[`references/delegation-protocol.md`](./references/delegation-protocol.md) for
the task schema + lifecycle + how @dom decomposes a program, and
[`references/bot-intake.md`](./references/bot-intake.md) for the instruction a
bot follows when it picks up @dom tasks.

## Files
- `SKILL.md` — when/how @dom delegates; the two-sided command surface.
- `scripts/delegate.py` — engine: add/list/intake/bots against bot TODO/memory.
- `scripts/delegate.sh` — thin wrapper (used by the `dom` command).
- `references/delegation-protocol.md` — schema, lifecycle, decomposition prompt.
- `references/bot-intake.md` — paste-ready bot-side intake instruction.
- Registry: `.github/dom-bots.json` (name → dir/todo/memory/owner/status).

## Quick start
```bash
dom bots                                           # roster
dom delegate job "Reinstall dom for telemetry" --priority P1 --verify "dom usage renders"
dom tasks                                          # counts across bots
dom intake job                                     # job's open @dom tasks
```

Bot repos resolve under `$DOM_WORKSPACE` (else the dom repo's parent dir).
Pure stdlib Python — no dependencies.
