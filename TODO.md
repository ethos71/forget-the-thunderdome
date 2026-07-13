# forget-the-thunderdome TODO

## @dom tasks — token-economy adoption (set by @dom 2026-07-10; the owning bot implements)

Governance: @dom (master plan: `~/workspace/dom/TODO.md`). @dom writes these
tasks; the owning bot implements them here. @dom does not run installs itself.

- [x] (2026-07-13) Install dom: ran `install.sh` from the local clone (offline
      equivalent of the curl one-liner). Adopted `sbz`/`ask` delegation + `dom usage`.
      Toolkit lives under `.github/` (commands, evals, dom-usage + eval-enforcement
      skills), `docs/robots/` memory architecture, `bin/dom-ship`. Free-tier routing
      goes to local Ollama; paid tiers only when needed.

## Shipped alongside adoption (2026-07-13)

- [x] **Ollama free tier in the product AI** (`src/ai_config.py`): three-tier
      waterfall — paid key → local Ollama (auto, no paid tool required) → none.
      crewAI + AutoGen consumers updated. Override model with `FTT_OLLAMA_MODEL`.
- [x] **Native MCP entry points** (`--mcp`) for `gmail-server`, `job-discovery`,
      `form-parser` — every server is now CLI *and* MCP. README + `.mcp.json.example`
      updated (moved off the roadmap).

## Remaining roadmap (README)

- [ ] Desktop launcher (Tauri/Electron) with first-run profile wizard
- [ ] Email providers beyond Gmail: Microsoft 365 / Outlook (Graph), generic IMAP
- [ ] Calendar: ICS export for interviews first, then Google/Microsoft adapters
- [ ] Dashboard HTML renderer (CLI dashboard works today)
