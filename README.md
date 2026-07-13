# forget-the-thunderdome

**Job hunting beyond Thunderdome.**

Two hundred candidates enter, one leaves — and the fight is LeetCode puzzles and AI
screeners instead of anything resembling engineering. Forget the Thunderdome. This
toolkit runs your job search against the companies that **don't** make you step into
the dome: no CoderPad gauntlets, no timed assessments, no talking to a bot before a
human reads your name.

Everything runs locally. Your pipeline lives in a SQLite file on your machine, your
email token stays on your machine, and your profile lives in one YAML file the repo
never commits.

## What it does

- **Job discovery** that validates postings by actually reading them — an HTTP 200
  doesn't mean a role is real or still open (`skills/job-search-validation/`)
- **Gauntlet filtering** — target hiring-without-whiteboards companies and skip
  LeetCode-gated front doors
- **Email tracking** — syncs recruiter email and classifies it (interview / offer /
  rejection) straight into your local pipeline (`mcp-servers/gmail-server/`)
- **Application tracking** — SQLite pipeline: applied, contacted, interviewing,
  offer; who owes you a reply and who you owe one (`src/job_cli.py`)
- **Cover letters** driven by *your* profile config — authentic, never generic
- **Form parsing** — extract application form fields and suggest answers from your
  profile (`mcp-servers/form-parser/`)
- **Agent-driven mode** — every piece is exposed as MCP servers; point Claude or
  GitHub Copilot at them and an AI agent runs the search loop with you

## Quickstart (engineers)

```bash
git clone https://github.com/ethos71/forget-the-thunderdome
cd forget-the-thunderdome
pip install -r src/requirements.txt

cp profile.yaml.example profile.yaml   # fill in who you are and what you want
python3 src/job_cli.py dashboard       # your pipeline (creates data/job_tracker.db)
python3 src/job_cli.py jobs            # scored postings
python3 src/job_cli.py follow-ups      # who needs a nudge
```

Email sync — Gmail, any IMAP mailbox, or Microsoft 365 / Outlook (Graph):

```bash
# Gmail (one-time OAuth setup: docs/providers/gmail-setup.md)
python3 mcp-servers/gmail-server/gmail_tracker.py --sync --days 30

# Any IMAP mailbox (Fastmail, iCloud, self-hosted, …) — set FTT_IMAP_* env,
# see docs/providers/imap-setup.md
python3 mcp-servers/imap-server/imap_tracker.py --sync --days 30

# Microsoft 365 / Outlook via Graph — set FTT_GRAPH_* env + register an Azure app,
# see docs/providers/microsoft-graph-setup.md
python3 mcp-servers/graph-server/graph_tracker.py --sync --days 30
```

All four servers classify recruiter mail into the same local pipeline and also run
as `--mcp` stdio servers.

## Agent mode

This toolkit was built to be driven by an AI agent, and every piece works two ways.

**Via the CLI** — open this repo in Claude Code (or Copilot with terminal access),
and the agent runs the loop — discover → validate (`skills/job-search-validation/`)
→ score → apply → track → follow up — by calling the same commands you would.

**Via MCP** — the gmail-server, job-discovery, and form-parser modules each run as a
stdio MCP server with a `--mcp` flag, so any MCP client can wire them in without
shell access:

```bash
python3 mcp-servers/gmail-server/gmail_tracker.py --mcp   # sync + classify email
python3 mcp-servers/job-discovery/scraper.py --mcp        # discover + score postings
python3 mcp-servers/form-parser/form_parser.py --mcp      # parse a form, suggest answers
```

Copy `.mcp.json.example` to `.mcp.json` (set `YOUR_PROJECT_ROOT`) to register all
three with your client. They run locally over stdio and share the same
`profile.yaml` and `data/job_tracker.db` as the CLI — nothing new leaves your
machine. The `--mcp` flag is purely additive; the CLI commands above still work
unchanged. Running as an MCP server needs the `mcp` package (`pip install mcp`); the
plain CLI does not.

## Just give me the app

A desktop launcher with a first-run profile wizard ships in `launcher/` — a windowed
app (no terminal) that writes your `profile.yaml` and runs the loop with buttons:

```bash
python3 launcher/ftt_launcher.py        # opens the GUI (needs a display)
python3 launcher/ftt_launcher.py --check  # headless self-check
```

To hand someone a double-click app with no Python install, freeze it per-OS with
PyInstaller — `launcher/build.sh` does this (see `launcher/README.md`).

## Roadmap

Shipped (see the sections above): native `--mcp` servers for gmail/job-discovery/
form-parser; **IMAP + Microsoft Graph email providers**; **HTML dashboard**
(`job_cli.py dashboard --html`); **ICS calendar export** (`job_cli.py calendar`);
**desktop launcher** with first-run profile wizard.

Still open:

- [ ] Calendar: native Google / Microsoft OAuth adapters (ICS export ships today)
- [ ] Microsoft Graph email: end-to-end verification + token refresh/backoff (the
      provider is scaffolded; needs an Azure app registration to exercise)
- [ ] Package the launcher into signed per-OS installers (PyInstaller/CI)

## Privacy

- `profile.yaml`, `data/`, and email tokens are gitignored from day one
- Nothing leaves your machine except the requests you make to job boards and your
  own email provider
- No telemetry, no accounts, no SaaS

## License

MIT — see [LICENSE](LICENSE).
