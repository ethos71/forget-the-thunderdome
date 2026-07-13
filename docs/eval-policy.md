# Eval Policy

Every project that installs `dom` ships behavior evals alongside its
behavior. Unit tests prove the code compiles. **Evals prove the code
still does the thing it claims to do.** They are not the same.

This file is the contract. The `dom-eval-enforcer` agent
(`agents/dom-eval-enforcer.md`) is the policy in agent form — it gets
copied into consuming projects so every other agent in the session can
defer to it.

## Where evals live

```
<project>/.github/evals/
├── README.md
├── run_all.py                — top-level runner; exit 0 = all green/skipped
├── ai/                       — LLM behavior (hallucination, refusal, citation)
├── tools/                    — MCP tool output contracts
├── skills/                   — Skill/orchestration rules + skill-shape + memory-arch
├── voice/                    — Voice/persona conformance
├── ui/                       — Page/route contracts
└── fixtures/                 — JSON inputs replayed by evals
```

Anything in `test/` is a unit test. Anything in `.github/evals/` is a
behavior eval. The two have different rules.

## Where workflow scripts live

```
<project>/
├── .github/
│   ├── scripts/              — helpers invoked ONLY by .github/workflows/*.yml
│   └── workflows/
└── bin/                      — operator + cron + systemd helpers
```

A script belongs in `.github/scripts/` when nothing outside a workflow
runs it (e.g. report parsers, issue creators, CI checkers). A script
belongs in `bin/` when a human or cron job runs it (e.g. daily
pipelines, health checks, manual ops). The enforcer agent treats
workflow-only scripts placed in `bin/` as drift.

## Rules every eval must follow

| Rule | Why |
|---|---|
| **Skip-safe** | If the oracle is missing (no API key, empty DB, off-season), exit 0 with a `⚠️ Skipping — <reason>` message. Never silent-pass by inventing data. |
| **Hermetic-ish** | Run against local data (SQLite, fixtures, or the in-repo LLM provider with a stated key). No drive-by network calls to third parties. |
| **Exit code is the verdict** | `0` = pass *or* skip. `1` = real regression. CI gates on this. |
| **Names the rule it pins** | Top docstring states the behavior under test and links the constitution principle or memory entry that codifies it. |
| **Oracle is real data** | Assertions compare to SQLite rows / fixture files / source AST — never to the model's own output. |
| **Failure is actionable** | When an eval fails, the output names the rule, the violating row(s), and the file to fix. |

## When you ship something, you ship an eval

A change qualifies as "shippable" only when:

1. **New MCP tool** → eval in `tools/test_<name>.py` pinning its output shape + invariants.
2. **New skill (orchestration rule)** → eval in `skills/test_<rule>.py` that fails when the rule is violated. An AST-level check is fine when the rule is a code shape (e.g. "X must call Y before Z").
3. **New agent persona / voice** → eval in `voice/test_<persona>.py` scoring real generated copy against the persona's banned-list + required signals.
4. **New LLM surface** → eval in `ai/test_<surface>_hallucinations.py` running adversarial probes against the oracle.
5. **New UI route** → entry in `ui/contracts/pages.yml`.

A new memory entry of type `feedback` is also a candidate: if the rule
is going to be cited in future sessions, it should be enforceable. Open
a follow-up eval task.

## Skill structure (load-bearing)

Every `.github/skills/<name>/` must hold this shape:

```
.github/skills/<name>/
├── SKILL.md           — frontmatter (name, description) + process docs
├── README.md          — When to Use + Key Scripts + References
├── references/*.md    — at least one reference doc
└── scripts/*.sh       — at least one executable helper
```

**Why this is non-negotiable:** the skill router (`help/SKILL.md`)
treats each subfolder as a discoverable skill. Without README +
references, the router has nothing to surface and the skill rots into
a SKILL.md-only stub.

Enforced by `.github/evals/skills/test_skill_shape.py` (template in
this repo at `templates/evals/skills/test_skill_shape.py`).

**Exempt list:** pure router skills with no scripts of their own
(typically `help`). Keep this exempt list tiny — every exemption is
technical debt.

## Memory architecture (load-bearing)

Every project must keep AI session memory under `docs/robots/`:

```
docs/robots/
├── README.md       — index + reading order
└── MEMORY.md       — 3-tier session memory (🔴 short / 🟡 mid / 🟢 long)
```

**Why this is non-negotiable:** fresh AI sessions orient by reading
`docs/robots/MEMORY.md` first. Moving it under `docs/` or renaming
breaks the contract for every agent that consumes the project. This
is the rule [[feedback_smartballz_md_at_root]]-style — a load-bearing
file path that's also a load-bearing convention.

Enforced by `.github/evals/skills/test_memory_architecture.py`
(template at `templates/evals/skills/test_memory_architecture.py`).

The eval requires:
- `docs/robots/README.md` exists and references `MEMORY.md`
- `docs/robots/MEMORY.md` exists and has all three tier markers (🔴 🟡 🟢)
- Soft warning if `MEMORY.md` "Last Updated:" is >30 days stale

## Anti-patterns (these are not evals)

- **Status-code "evidence".** An exit code, a `200`, a "health_check
  passed" row, a timestamp. None of these prove behavior. Only data
  content (real player names, real article text, real lineup rows)
  proves anything. (See `feedback_no_status_code_evidence`.)
- **Silent fallbacks under failure.** If the oracle is unavailable,
  *skip* — don't degrade to a weaker signal that "looks fine".
- **Self-referential assertions.** Asserting the model said what it
  said. The oracle has to be external data.
- **Snapshot tests on raw LLM output.** They go stale the moment
  prompts move. Score against rules, not strings.

## How an agent should respond to this policy

When you (the agent) are about to write code that affects any of the
five shippable categories above, do this first:

1. **Read `.github/evals/README.md`** in the consuming project for the
   local conventions.
2. **Look for an existing eval** in the relevant bucket. If one exists,
   extend it. If not, write one — in the same change as the behavior.
3. **Run `python .github/evals/run_all.py`** before reporting done.
4. **If an eval fails on existing data**, surface that as a real
   finding — don't loosen the eval to make it pass.
5. **Adding or modifying a skill?** Run
   `python .github/evals/skills/test_skill_shape.py` and confirm
   the result.

## How to write a good eval (10 minutes)

1. Open the persona/skill/tool doc. Pick the most concrete rule.
2. Find the oracle: SQLite table, fixture file, or source-AST shape.
3. Write the smallest possible script that fails when the rule fails,
   skips cleanly when the oracle is missing, passes silently otherwise.
4. Sample real data, don't generate fresh — the cost of a slow eval
   is that it stops getting run.
5. Put it in `.github/evals/<bucket>/test_<name>.py` and register it
   in `run_all.py`.

If you want a starting point, `templates/evals/` in this repo has
skeleton files for each bucket.
