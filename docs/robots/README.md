# `<project>` — AI Robot Memory

AI assistants: **READ THESE FILES FIRST** before making changes.

## Memory System (3 Tiers)

| Tier | File | Update Frequency | Purpose |
|------|------|-----------------|---------|
| 🔴 **Short-Term** | [MEMORY.md](MEMORY.md) §1 | Every session | Active work, current issues, recent changes |
| 🟡 **Mid-Term** | [MEMORY.md](MEMORY.md) §2 | When patterns emerge | Conventions, gotchas, code patterns |
| 🟢 **Long-Term** | [MEMORY.md](MEMORY.md) §3 | On milestones | Architecture decisions, completed features |

## Build Logs

Every bug, fix, and decision is recorded in [`docs/buildlogs/`](../buildlogs/README.md)
(if the project uses that convention).

**AI assistants:** Before starting work, check buildlogs for past
solutions to similar problems.

## Reading Order

1. **[MEMORY.md](MEMORY.md)** — Current state, conventions, architecture
2. **[../buildlogs/](../buildlogs/README.md)** — Past issues and solutions
3. **[LESSONS_LEARNED.md](LESSONS_LEARNED.md)** — Historical lessons (if present)

## Topic-specific design docs

Add any topic-specific files here as separate markdown documents.
Pattern: one concept per file, named in SCREAMING_SNAKE_CASE.

## Enforcement

The `dom-eval-enforcer` agent (`.github/agents/dom-eval-enforcer.md`)
expects:

- `docs/robots/README.md` (this file) present + lists current tiers
- `docs/robots/MEMORY.md` present + has all 3 tier sections
- The "Last Updated" line in MEMORY.md within 30 days of HEAD

The skill-shape eval treats `docs/robots/MEMORY.md` as load-bearing —
moving it under `docs/` or renaming breaks the contract.
