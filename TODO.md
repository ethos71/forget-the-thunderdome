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
