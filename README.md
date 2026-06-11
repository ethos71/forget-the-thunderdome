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

Email sync (Gmail today; more providers on the roadmap):

```bash
# one-time OAuth setup: docs/providers/gmail-setup.md
python3 mcp-servers/gmail-server/gmail_tracker.py --sync --days 30
```

## Agent mode

This toolkit was built to be driven by an AI agent. Today that works through the
CLI: open this repo in Claude Code (or Copilot with terminal access), and the agent
runs the loop — discover → validate (`skills/job-search-validation/`) → score →
apply → track → follow up — by calling the same commands you would.

Native MCP server entry points (so any MCP client can wire in without shell access)
are on the roadmap; `.mcp.json.example` sketches the planned shape.

## Just give me the app

A cross-platform desktop launcher (Windows / macOS / Linux — no terminal, no Python
install, guided email setup) is on the roadmap. Until then, the Quickstart above is
the path.

## Roadmap

- [ ] Native MCP server entry points (`--mcp`) for gmail-server, job-discovery, form-parser
- [ ] Desktop launcher (Tauri/Electron) with first-run profile wizard
- [ ] Email providers beyond Gmail: Microsoft 365 / Outlook (Graph), generic IMAP
- [ ] Calendar: ICS export for interviews first, then Google/Microsoft adapters
- [ ] Dashboard HTML renderer (CLI dashboard works today)

## Privacy

- `profile.yaml`, `data/`, and email tokens are gitignored from day one
- Nothing leaves your machine except the requests you make to job boards and your
  own email provider
- No telemetry, no accounts, no SaaS

## License

MIT — see [LICENSE](LICENSE).
