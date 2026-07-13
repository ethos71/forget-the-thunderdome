# Usage log format & enforcement rules

## The log
`delegate_task` appends one JSON object per line (JSONL) to the usage log for
every **real** model call — i.e. after `client.chat.completions.create`
returns, before any edit-parsing can fail. So the log captures every token
that actually hit a model, even when the resulting edit was rejected.

Location (first match wins):
1. `--log PATH` argument
2. `$DOM_USAGE_LOG`
3. `<project-root>/.dom/usage.jsonl` (default; gitignored)

The classifier's own routing call runs on local Ollama (free) and is **not**
logged — only the delegation call is. Interactive `ask` Q&A is likewise
unlogged and free.

## Record schema
```json
{
  "ts": "2026-07-09T17:00:00+00:00",   // ISO-8601 UTC, when the call returned
  "purpose": "delegation",              // delegation | routing | adhoc
  "requested": "auto",                  // caller's model arg before resolution
  "model": "anthropic/claude-haiku-4-5",// resolved model id actually called
  "backend": "ollama" | "openrouter",   // free (local) vs paid (remote)
  "complexity": "SIMPLE",               // classifier verdict, or null if model forced
  "ollama_up": true,                    // was local Ollama reachable at call time
  "prompt_tokens": 700,
  "completion_tokens": 120,
  "total_tokens": 820,
  "latency_s": 6.42,                    // wall-clock seconds for the API call
  "est_cost_usd": 0.0013                // 0.0 for ollama; null if rate unknown
}
```

Field notes:
- `purpose`: `"delegation"` = a real code task via `delegate_task`;
  `"routing"` = the local classifier call itself (free, but its latency is
  real routing overhead); `"adhoc"` = `ask_local` Q&A. The savings and
  cost-vs-time sections use `latency_s`; enforcement only judges paid calls.
- `requested` is `"auto"` when the four-tier waterfall chose the model, or an
  explicit alias (`ollama`/`haiku`/`sonnet`/`opus`) / full id when the caller
  forced one. This is how the audit tells a routing decision from an override.
- `complexity` is `null` when the caller forced a model (no classification ran).
- `latency_s` is `null` on records written before latency tracking existed.
- `aborted: true` + `abort_signal` (optional): the process was killed
  (SIGTERM/SIGINT/SIGHUP) mid-model-call — e.g. a short foreground shell
  timeout hit a slow local model. Token counts are 0, `latency_s` is the
  partial wall-clock. SIGKILL cannot be logged. The report counts these under
  `purpose: aborted N`.
- `est_cost_usd` uses the `_OPENROUTER_RATES` table in `agent_tools.py`
  (USD per 1M tokens, input/output). Token counts are exact; dollar figures
  are estimates — update the table to match your OpenRouter plan.

## Enforcement rules (what the audit flags)
The routing contract (`docs/routing-guide.md`) says SIMPLE work must run free
on local Ollama. The audit classifies each **paid** (`backend:"openrouter"`)
call:

| Condition | Verdict | Meaning |
|-----------|---------|---------|
| `complexity` ∈ {SIMPLE} | **VIOLATION** (exit 1) | Free-tier task billed to a paid model — the router paid for work Ollama should do free. |
| `requested == "auto"` and `ollama_up == false` | **warning** | Auto-router couldn't reach the free tier and fell back to paid. Not a code bug — start `ollama serve`. |
| otherwise (MEDIUM/COMPLEX/ARCHITECTURAL, or a deliberate override) | OK | Paid model is the contract-correct tier. |

`SIMPLE` is the only tier required to be free — `_FREE_TIERS` in `usage.py`.
If your contract also forces MEDIUM onto local models, add `"MEDIUM"` there.

## Extending
- **More models / real prices:** edit `_OPENROUTER_RATES` in `agent_tools.py`.
- **Meter forced overrides:** a paid call with `requested != "auto"` is a human
  choosing to spend; the audit leaves it alone. To flag over-use of `opus`,
  add a rule keyed on `requested == "opus"`.
- **Dashboards:** `usage.sh --json` emits `{aggregate, audit}` for ingestion.
- **Rotation:** the log grows ~1 line per delegated task; truncate or rotate
  `.dom/usage.jsonl` freely — the report simply reflects whatever remains.
