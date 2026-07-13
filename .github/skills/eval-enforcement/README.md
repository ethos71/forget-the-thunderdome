# Eval Enforcement Skill

Human-facing entry point for the four policy contracts dom enforces.
The agent-facing version is in `SKILL.md`.

## When to Use

- Adding a new MCP tool, skill, agent persona, voice profile, or
  LLM-backed surface.
- Renaming or removing any of the above (the matching eval may need
  to be updated, not deleted).
- Editing a behavior contract — persona text, tool semantics, voice
  rules.
- Adding a workflow that calls a script (`.github/scripts/` vs `bin/`
  placement matters).
- Resolving a `feedback` memory entry by claiming "we now do X" —
  there should be an eval pinning X.

## Key Scripts

- `scripts/check-skill-shape.sh` — Run the universal skill-shape eval
  against this repo.
- `scripts/check-memory.sh` — Run the universal memory-architecture
  eval against this repo.
- `scripts/check-policy.sh` — Run both, plus any project-local evals.

## References

- `references/eval-buckets.md` — Which bucket (`ai`, `tools`, `skills`,
  `voice`, `ui`) a new eval belongs in.
- `references/enforcer-verdicts.md` — The three verdict shapes
  `@dom-eval-enforcer` returns.

## Related

- Agent: `.github/agents/dom-eval-enforcer.md`
- Contract: `docs/eval-policy.md`
- Universal evals: `.github/evals/skills/test_skill_shape.py`,
  `.github/evals/skills/test_memory_architecture.py`
