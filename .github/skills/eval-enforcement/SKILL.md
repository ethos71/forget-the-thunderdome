---
name: eval-enforcement
description: >-
  Gate any new MCP tool, skill, agent persona, voice profile, or LLM-backed
  surface behind a behavior eval before shipping. Also enforces skill shape,
  memory architecture, and workflow-script placement. Invoke when adding,
  renaming, or relaxing any of the above.
---

# Eval Enforcement

Owns the four contracts dom pins on every consumer project: behavior
evals, skill structure, memory architecture, and workflow-script
placement. This skill is dom's own — it both demonstrates the shape
the universal `test_skill_shape.py` enforces, and routes incoming
"can we ship this?" questions to the right answer.

The work itself is done by the `@dom-eval-enforcer` agent
(`.github/agents/dom-eval-enforcer.md`). This skill is the discovery
surface — when an agent or human is unsure whether a change is
ship-ready, they land here.

## Process

1. **Classify the change.** Is the diff adding any of:
   - An `@mcp.tool()` registration? → behavior eval required.
   - A new `.github/skills/<name>/` directory? → shape eval gates it.
   - A new agent persona / voice doc / system prompt? → eval required.
   - A new LLM-backed route or surface? → eval required.
   - A move of `docs/robots/MEMORY.md`? → ship-block.
   - A workflow that calls a script? → placement check.
2. **Run the relevant gate.**
   - `scripts/check-skill-shape.sh` — runs `test_skill_shape.py` on the
     current repo.
   - `scripts/check-memory.sh` — runs `test_memory_architecture.py`.
   - `scripts/check-policy.sh` — runs both, plus any project-local
     evals under `.github/evals/`.
3. **Consult `@dom-eval-enforcer`** with the diff if the change touches
   a behavior contract (persona text, tool semantics, voice profile).
   The agent returns one of: "ship it", "add an eval first", "don't
   ship". See `references/enforcer-verdicts.md` for verdict shapes.
4. **Write or update the eval.** Land in the right bucket under
   `.github/evals/<bucket>/`: `ai/` (LLM surfaces), `tools/` (MCP
   tools), `skills/` (skill shape), `voice/` (personas), `ui/` (routes).
   Reference: `references/eval-buckets.md`.
5. **Re-run** until pass/skip is clean. Exit-code-only evidence is
   not acceptable — the eval must compare against real data content.

## Key Files

- `.github/agents/dom-eval-enforcer.md` — Policy agent persona.
- `.github/evals/skills/test_skill_shape.py` — Universal skill-shape eval.
- `.github/evals/skills/test_memory_architecture.py` — Universal memory eval.
- `docs/eval-policy.md` — The formal contract.
- `docs/robots/MEMORY.md` — Mid-term tier records prior enforcement decisions.

## Related Skills

- (none yet — dom currently ships exactly one skill of its own; consumer
  projects like smartballz layer dozens more)

## Hard Rules

- An eval that returns 0 without comparing real data is dead weight.
  Delete it or fix it; don't ship it.
- A skill without a `references/*.md` and a `scripts/*.sh` is a stub,
  not a skill. The shape eval will fail.
- `docs/robots/MEMORY.md` is sacred — renaming or relocating it is a
  ship-block.
- Workflow-only helpers belong in `.github/scripts/`. Operator/cron
  scripts belong in `bin/`. Don't mix.
- Never soften an eval threshold to unblock a ship. If the eval fails
  on current data, fix the data or the behavior.
