---
name: dom-usage
description: Report AI token usage, cost, and latency per model and audit that Ollama routing is being enforced. Use when you want to know what tokens/cost went to which model (Ollama vs Haiku/Sonnet/Opus via OpenRouter), what Ollama saved vs paid tiers, the cost-vs-time tradeoff, or to verify the four-tier waterfall is keeping cheap/free work on local Ollama. Invoked as `dom usage` (named dom-usage to avoid colliding with Claude Code's built-in /usage). Reads the log that delegate_task/ask_local write.
---

# dom-usage

Answers four questions for any project that delegates work through dom's
`dom task` / `delegate_task` / `ask_local` router:

1. **What tokens are going to what models?** — per-model table (calls,
   tokens, estimated cost, wall-clock time) with a grand total.
2. **Is Ollama being enforced correctly?** — the free-vs-paid split plus a
   list of any task that was billed to a paid model when the routing
   contract said it should have run free on local Ollama.
3. **What did Ollama save us?** — the free tokens re-priced at Haiku /
   Sonnet / Opus rates vs actual paid spend.
4. **What did the savings cost in time?** — measured Ollama latency vs paid
   latency, expressed as dollars saved per extra minute waited.

## Where the data comes from
`delegate_task` and `ask_local` (`.github/mcp/tools/agent_tools.py`) append
one JSON line per **real model call** to `.dom/usage.jsonl`: model, backend
(`ollama` = free / `openrouter` = paid), purpose
(`delegation`/`routing`/`adhoc`), the classifier's complexity verdict,
whether Ollama was up, token counts, latency, and estimated USD cost.
The shell `ask` helper is local/free but not yet logged — prefer
`ask_local` when you want metered Q&A.

If there's no log yet, nothing has been delegated — run a task first:
```bash
dom task path/to/file 'some change' 'echo test'
```

## Run it
```bash
dom usage                  # via the umbrella command (preferred); `dom --usage` also works
dom usage --since 7        # last 7 days only
dom usage --json           # machine-readable aggregates (for CI/dashboards)
dom usage --md             # markdown-wrapped, for saving as a report file
dom usage --log PATH       # point at a specific usage.jsonl
dom usage --bot smartballz # ANOTHER bot's report (resolves via .github/dom-bots.json)
# equivalent direct path: .github/skills/dom-usage/scripts/usage.sh
```

`--bot <name>` lets @dom pull any registered bot's report without leaving its
own repo — e.g. `@dom --usage smartballz` → `dom usage --bot smartballz`. It
reads that bot's `.dom/usage.jsonl` under the workspace root (`$DOM_WORKSPACE`
or the dom repo's parent dir); reading a log never modifies the bot's repo.

Log location is autodetected: `--log` > `$DOM_USAGE_LOG` > the nearest
`.dom/usage.jsonl` walking up from the working directory.

## Reading the enforcement verdict
- **PASS** — no free-tier (SIMPLE) task hit a paid model. Routing is holding.
- **PASS (with warnings)** — no misrouted work, but some calls were forced to
  a paid model because **Ollama was down** (`ollama_up:false`). Start
  `ollama serve` so the free tier is available; nothing was misrouted by the
  code.
- **FAIL** — a SIMPLE task was billed to OpenRouter. That's money spent on
  work Ollama should do for free. The exit code is `1`, so you can gate CI on
  it. Investigate the offending call (a forced `model=` override, or a
  classifier that mislabeled the task).

## What this skill does NOT do
- It does not meter Claude Code's own orchestrator tokens (this session) —
  use Claude Code's built-in `/usage` for that (which is why this command is
  `dom usage`, not `/usage`). It meters the **delegated** tier — the models
  `dom task`/`delegate_task`/`ask_local` call on your behalf. That's the tier dom
  exists to keep cheap.
- OpenRouter costs are **estimates** from a rate table in `agent_tools.py`
  (`_OPENROUTER_RATES`, USD per 1M tokens). Edit it to match your plan; token
  counts are exact.

See `references/usage-log-format.md` for the record schema, the enforcement
rules, and how to extend the audit.
