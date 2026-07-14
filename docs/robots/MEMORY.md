# forget-the-thunderdome — AI Session Memory

**Purpose:** Structured memory for AI assistants working on this project.
Read this FIRST before making any changes. It prevents repeating mistakes.

**Last Updated:** 2026-07-14

---

## 🔴 Short-Term Memory (Current Sprint)

Active work and immediate context. Update every session.

### Current State

- Product: local-first job-search toolkit ("job hunting beyond Thunderdome") —
  discover → validate → score → apply → track → follow up. Everything runs on the
  user's machine; pipeline is a SQLite file, email token + `profile.yaml` never leave.
- Frontend stack: none (CLI-first; `dashboard/` is a shell refresh script, HTML
  renderer still on the roadmap).
- Backend stack: Python 3.12. Product code in `src/` (crewAI + AutoGen agents).
  MCP servers in `mcp-servers/{gmail-server,job-discovery,form-parser}/`.
- Service / deployment: none — runs locally, no SaaS, no telemetry, no accounts.
- DB: SQLite at `data/job_tracker.db` (gitignored).
- Tests / evals: dom universal evals under `.github/evals/` (installed 2026-07-13).
  Gate: `.github/skills/eval-enforcement/scripts/check-policy.sh`.

### Active Issues

- Roadmap sweep shipped (see Completed features) — genuinely open now: native
  Google/Microsoft calendar OAuth adapters (ICS export ships), Microsoft Graph
  email end-to-end verification (scaffolded; needs an Azure app), launcher
  installer packaging (PyInstaller/CI).
- `ollama-max` program (account downgrade): product AI is local-first as of
  2026-07-14 (`DOM-20260714-1`, done here).

---

## 🟡 Mid-Term Memory (Conventions)

Patterns, gotchas, and rules of thumb. Update when a pattern emerges
or a rule is established.

### Conventions

- **Three-tier AI waterfall — LOCAL-FIRST** (`src/ai_config.py`): **local Ollama**
  (auto, whenever `ollama serve` is reachable — preferred *even when a paid key is
  set*) → paid provider (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`, used only when Ollama
  is down) → none. Escape hatch: `FTT_FORCE_PAID=1` forces the paid tier even with
  Ollama up. Flipped from paid-first 2026-07-14 (`DOM-20260714-1`, ollama-max /
  account-downgrade). Override the local model with `FTT_OLLAMA_MODEL`.
- **CLI + MCP dual surface**: every server (`gmail-server`, `job-discovery`,
  `form-parser`) runs as a plain CLI *and* as a native stdio MCP server via `--mcp`.
  `.mcp.json.example` wires them into any MCP client. `mcp` import is lazy (inside
  the `--mcp` branch) so the CLI works without the package.
- **dom token-economy adopted** (2026-07-13): `dom task` / `dom ask` / `dom usage`
  available for dev-time delegation — SIMPLE tasks route to free local Ollama, harder
  tiers to paid only when needed. Just run `dom <command>`, or source the shell tools:
  `source .github/commands/dom-tools.sh`.
- `profile.yaml`, `data/`, email tokens, and `.dom/` are gitignored from day one.

### Gotchas

- The dom installer overwrites `.mcp.json.example` with its own dom-agent config —
  FTT's version (3 servers + dom-agent) is the source of truth; don't let a re-install
  clobber it silently.
- `get_provider()` returns `("ollama", None)` in the local tier — callers that unpack
  `(provider, api_key)` must tolerate a `None` key.

---

## 🟢 Long-Term Memory (Architecture)

Major decisions and the reasoning behind them. Update on milestones.

### Architecture decisions

- **Local-first, privacy-first** — nothing leaves the machine except the user's own
  requests to job boards and their email provider. This is the product's whole thesis.
- **Ollama as the default, not just the floor** — the toolkit runs on a local model
  whenever one is reachable, preferring it over any configured paid key (flipped
  local-first 2026-07-14 for the account-downgrade program). It still works for users
  with no paid AI subscription; `FTT_FORCE_PAID=1` is the deliberate opt-in to paid.
- **Adopted the dom toolkit** instead of rolling bespoke cost controls — same routing
  engine (`agent_tools.py`), evals, and memory architecture as the rest of the fleet.

### Completed features

- 2026-07-13 — Adopted dom toolkit (`install.sh`): `dom task`/`dom ask`/`dom usage`,
  universal evals, memory architecture, eval-enforcement gate. (FTT TODO task closed.)
  Re-installed 2026-07-13 across the toolkit rename — surface is now `dom <command>`;
  the old shell-tool name ships only as a deprecated shim.
- 2026-07-13 — Ollama free-tier fallback in `src/ai_config.py` (+ crewAI/AutoGen consumers).
- 2026-07-14 — Flipped the product-AI waterfall to LOCAL-FIRST (`DOM-20260714-1`,
  ollama-max): reachable Ollama wins even with a paid key set; paid only when Ollama
  is down or `FTT_FORCE_PAID=1`. Updated crewAI/AutoGen guidance strings + this memory.
- 2026-07-13 — Native `--mcp` entry points for gmail-server, job-discovery, form-parser
  (moved off the roadmap; README + `.mcp.json.example` updated).
- 2026-07-13 — Roadmap sweep (agents fanned out):
  - HTML dashboard renderer — `job_cli.py dashboard --html` → `src/dashboard_html.py`
    (self-contained, dependency-free).
  - ICS calendar export — `job_cli.py calendar` → `src/calendar_export.py` (hand-written
    RFC-5545, all interviews). Google/MS OAuth adapters still open.
  - Email providers beyond Gmail: generic IMAP (`mcp-servers/imap-server/`, stdlib, full)
    and Microsoft Graph (`mcp-servers/graph-server/`, scaffold — needs Azure app + `msal`).
    Both share the gmail classification categories and run as `--mcp` servers.
  - Desktop launcher — `launcher/ftt_launcher.py` (Tkinter GUI + first-run profile wizard;
    Tk imported lazily so it imports headless; `--check` for CI). Tauri ruled out (no Rust);
    PyInstaller freeze is the documented no-Python packaging step (`launcher/build.sh`).

---

## Cross-references

- Eval policy: `docs/eval-policy.md`
- Enforcement agent: `.github/agents/dom-eval-enforcer.md`
- dom usage / cost audit: `.github/skills/dom-usage/`
- Product AI config: `src/ai_config.py`
- MCP servers: `mcp-servers/*/` (each supports `--mcp`)
