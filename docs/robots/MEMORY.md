# forget-the-thunderdome — AI Session Memory

**Purpose:** Structured memory for AI assistants working on this project.
Read this FIRST before making any changes. It prevents repeating mistakes.

**Last Updated:** 2026-07-13

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

- Remaining roadmap: desktop launcher (Tauri/Electron), email providers beyond
  Gmail (M365/Graph, IMAP), calendar ICS export, dashboard HTML renderer.

---

## 🟡 Mid-Term Memory (Conventions)

Patterns, gotchas, and rules of thumb. Update when a pattern emerges
or a rule is established.

### Conventions

- **Three-tier AI waterfall** (`src/ai_config.py`): paid provider
  (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`) → **local Ollama free tier** (auto, when
  no paid key and `ollama serve` is reachable) → none. No paid tool required to use
  the AI features. Override the local model with `FTT_OLLAMA_MODEL`.
- **CLI + MCP dual surface**: every server (`gmail-server`, `job-discovery`,
  `form-parser`) runs as a plain CLI *and* as a native stdio MCP server via `--mcp`.
  `.mcp.json.example` wires them into any MCP client. `mcp` import is lazy (inside
  the `--mcp` branch) so the CLI works without the package.
- **dom token-economy adopted** (2026-07-13): `sbz` / `ask` / `dom usage` available
  for dev-time delegation — SIMPLE tasks route to free local Ollama, harder tiers to
  paid only when needed. Source shell tools: `source .github/commands/sbz-tools.sh`.
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
- **Ollama as the free floor** — rather than gating AI behind a paid key, the toolkit
  falls back to a local model so it works for users with no paid AI subscription.
- **Adopted the dom toolkit** instead of rolling bespoke cost controls — same routing
  engine (`agent_tools.py`), evals, and memory architecture as the rest of the fleet.

### Completed features

- 2026-07-13 — Adopted dom toolkit (`install.sh`): `sbz`/`ask`/`dom usage`, universal
  evals, memory architecture, eval-enforcement gate. (FTT TODO task closed.)
- 2026-07-13 — Ollama free-tier fallback in `src/ai_config.py` (+ crewAI/AutoGen consumers).
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
