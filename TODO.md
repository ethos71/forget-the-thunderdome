# forget-the-thunderdome TODO

Only open work lives here. Shipped items are recorded in the README "Roadmap"
section and `docs/robots/MEMORY.md`, not repeated here.

## Open

- [ ] Calendar: native Google / Microsoft OAuth adapters (local ICS export ships today)
- [ ] Microsoft Graph email: end-to-end verification + token refresh/backoff (provider
      is scaffolded; needs an Azure app registration to exercise — see
      `docs/providers/microsoft-graph-setup.md`)
- [ ] Package the desktop launcher into signed per-OS installers (PyInstaller/CI)

## 📋 @dom delegated tasks

<!-- Managed by `dom delegate`. @dom writes these; this bot implements, checks them off, and commits. `dom intake` lists your open ones. -->

- [x] `DOM-20260713-1` **(P1)** toolkit-surface rename to `dom` — adopted: re-ran
      install.sh (pulled dom-tools.sh + deprecated shim), migrated this repo's
      ~/.bashrc line to dom-tools.sh, cleared the old naming from repo-authored files
      (only toolkit shims remain), eval gate green, Ollama audit 100% free. Done
      2026-07-13 (commit d46dfba). _[done]_
- [x] `DOM-20260713-2` **(P1)** PRIVACY LEAK — the private @dom roster
      (`.github/dom-bots.json`) had been committed into this PUBLIC repo by the
      toolkit install. Fixed: removed it from the tree, gitignored it, and scrubbed it
      from ALL git history (git-filter-repo) + force-pushed; also genericized
      `agent_tools.py get_context()` which hardcoded another project's data. Verified:
      roster file untracked + absent from every commit (bot dirs/owners/third-party
      repos all return 0 in history); a clone can no longer retrieve the roster.
      Residual: generic toolkit code still references the registry *key* (`reg["bots"]`)
      and a few `@smartballz` example mentions remain — no roster data; durable fix is
      upstream in dom (don't ship the roster / @dom-side code / example bot to public
      consumers). Done 2026-07-13. _[privacy-leak done]_
- [ ] `DOM-20260714-1` **(P1)** OLLAMA-MAX (account-downgrade program): flip the product-AI waterfall in src/ai_config.py to LOCAL-FIRST. Today paid wins (OPENAI_API_KEY present -> gpt-4o-mini) and Ollama is only the fallback; invert it: if Ollama is reachable -> ('ollama', None) tier even when a paid key exists; paid ONLY when FTT_FORCE_PAID=1 (or Ollama down); none-tier unchanged. Update the crewAI/AutoGen guidance strings + README AI section + docs/robots/MEMORY.md convention note (currently documents paid-first). Dev-side: keep delegate-first (dom task / dom ask) for mechanical edits; keep ollama serve running (see dom docs/ollama-keepalive.md). Implement in ONE Opus session; routine work thereafter stays local.  _[ollama-max]_
      ↳ verify: `with OPENAI_API_KEY set AND ollama up: get_provider()==('ollama',None) and get_openai_config() points at localhost:11434; FTT_FORCE_PAID=1 -> ('openai',key); eval gate green; dom usage enforcement PASS`
      ↳ set by @dom 2026-07-14 (owner @thunderdome)
