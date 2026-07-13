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

- [ ] `DOM-20260713-1` **(P2)** sbz->dom rename (Dominick: nothing is called sbz, it is all dom). DOWNSTREAM of the toolkit rename DOM-20260713-2 - do NOT start until that ships (it provides dom-tools.sh + deprecated sbz shims + a bumped version). Then: (1) re-run install.sh to pull the dom-named tooling; (2) fix repo-local sbz references listed below; (3) update THIS repo line in ~/.bashrc that sources .../sbz-tools.sh -> dom-tools.sh; (4) run the eval gate green. HOLD until Dominick triggers the whole fleet at once.  NOTE: this repo is now PUBLIC (launched 2026-07-13) - no sbz naming should remain visible in the public tree. LOCAL REFS: docs/robots/MEMORY.md plus the installed .github toolkit files (commands, dom-usage skill docs, mcp/tools/agent_tools.py).  _[sbz2dom]_
      ↳ verify: `grep -rI "\bsbz" tracked NON-generated files returns nothing (or only clearly-deprecated shims shipped by the toolkit); check-policy.sh green; this repo ~/.bashrc line sources dom-tools.sh not sbz-tools.sh; public tree shows no sbz`
      ↳ set by @dom 2026-07-13 (owner @thunderdome)
