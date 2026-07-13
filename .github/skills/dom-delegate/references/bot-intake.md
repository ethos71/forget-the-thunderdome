# Bot intake instruction (@dom subordinates)

Paste-ready instruction for a subordinate bot's agent file / session start.
It tells the bot how to pick up and complete tasks @dom delegated to it.

---

## You have a boss: @dom

@dom (the orchestrator) delegates work to you by writing tasks into **your**
`TODO.md` (repo root) — under a `## 📋 @dom delegated tasks` section — and
sometimes into your memory. You implement them. @dom never writes your code;
you own your repo.

### On session start / when asked to "check @dom tasks"
1. Run `dom intake <your-bot-name>` (or read the `## 📋 @dom delegated tasks`
   section of your `TODO.md`). If `dom` isn't installed yet, that may itself
   be your first task.
2. Pick the **highest-priority open** task (P1 before P2 before P3).
3. Read its `↳ verify:` line — that's your definition of done.

### Implementing a task
4. Do the work in your own repo, on a branch if it's risky or the repo is live.
5. **Verify** exactly what the task's `verify:` line says (run the command /
   confirm the observable). Don't check the box until it passes.
6. Check the box: `- [ ]` → `- [x]` on that task line. Leave the ID intact.
7. Commit (your repo's normal flow — pass your own pre-commit gates).
8. If the task was token/telemetry-related, run `dom usage` and confirm the
   enforcement verdict is PASS.

### Reporting back
- Checking the box IS the report — `dom tasks` lets @dom see your done count.
- If a task is wrong, blocked, or under-specified, DON'T silently skip it:
  add a `↳ blocked: <reason>` line under it and leave it open, so @dom sees it.
- Never edit another bot's TODO/memory. Never delegate — that's @dom's job.

### The standing rule (why these tasks exist)
Keep cheap work cheap: delegate SIMPLE/MEDIUM single-file edits to `sbz`
(local Ollama first), keep `ollama serve` running, and run `dom usage` weekly
so no free-tier work is billed to a paid model. That's the program @dom is
rolling out; your delegated tasks are your slice of it.
