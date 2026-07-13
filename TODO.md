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
