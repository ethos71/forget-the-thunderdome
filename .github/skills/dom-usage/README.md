# dom-usage skill

Token & cost reporting plus an Ollama-enforcement audit for dom's delegation
tier. Give this to any agent (or human) that needs to see where the money is
going and confirm the four-tier waterfall is keeping cheap work free.

See [`SKILL.md`](./SKILL.md) for when to use it and how to read the verdict,
and [`references/usage-log-format.md`](./references/usage-log-format.md) for
the log schema and audit rules.

## Files
- `SKILL.md` — entry point: what it answers, how to run it, verdict meanings.
- `scripts/usage.sh` — thin wrapper; runs the analyzer with your flags.
- `scripts/usage.py` — reads `.dom/usage.jsonl`, aggregates per model,
  audits Ollama enforcement, prints the report. Stdlib only.
- `references/usage-log-format.md` — record schema + enforcement logic.

## Quick start
```bash
# after some delegated work has run (sbz / delegate_task):
dom usage            # full report
dom usage --since 30 # last 30 days
dom usage --json     # for a dashboard or CI gate
```

Exit code is `0` on a clean audit and `1` when a free-tier task was billed to
a paid model, so this doubles as a CI cost-guard.

## How it hooks in
The report is only as complete as the log. `delegate_task` in
`.github/mcp/tools/agent_tools.py` writes one line per real model call to
`.dom/usage.jsonl` (gitignored). No extra setup — running `sbz` populates it.
