# Evals

Behavior evals for this project. Read `docs/eval-policy.md` (installed
by `dom`) for the contract.

Plain unit tests live in `test/`. The two are not interchangeable.

## Layout

```
.github/evals/
├── ai/        — LLM behavior (hallucination, refusal, citation)
├── tools/     — MCP tool output contracts
├── skills/    — Skill/orchestration rules
├── voice/     — Persona / voice conformance
├── ui/        — Page/route contracts (Playwright + pages.yml)
├── fixtures/  — JSON inputs replayed by evals
└── run_all.py — top-level runner
```

## Running

```bash
python .github/evals/run_all.py             # all suites
python .github/evals/run_all.py --only ai   # one bucket
```

## Adding a new eval

See `docs/eval-policy.md` for the contract. The short version:

1. Pick the bucket.
2. Write `.github/evals/<bucket>/test_<name>.py`.
3. Register it in `run_all.py`.
4. Skip cleanly when the oracle is missing; exit 1 only on real regressions.

The `dom-eval-enforcer` agent (`.github/agents/dom-eval-enforcer.md`)
will gate ships on this — consult it before declaring an agent / tool
/ skill / voice / LLM-surface change done.
