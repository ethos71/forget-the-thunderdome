# Generic IMAP Provider Setup

Connect **any** IMAP mailbox (Fastmail, iCloud, Gmail-via-app-password, a
self-hosted server, your company's Outlook-over-IMAP, …) to the ftt job
tracker. Recruiter/job email is fetched, classified, and synced into the shared
pipeline DB — the same categories the Gmail provider produces
(`interview_invite`, `offer`, `rejection`, `recruiter_outreach`,
`application_update`).

Unlike the Gmail and Microsoft Graph providers, **IMAP needs no OAuth app and
no third-party Python packages** — it uses only the standard library
(`imaplib` + `email`). The only optional dependency is `mcp`, for the
`--mcp` server mode.

---

## Step 1: Get an app password

Most providers require an **app password** (a per-application secret) rather
than your normal login password, especially when 2FA is on. Never put your
real account password in an environment variable.

- **Gmail** (via IMAP instead of the OAuth provider):
  - Enable 2-Step Verification, then visit
    <https://myaccount.google.com/apppasswords> and create an app password.
  - Host: `imap.gmail.com`, Port: `993`.
- **Fastmail**:
  - Settings → Privacy & Security → Integrations → *New app password*
    (grant it "Mail" / IMAP access).
  - Host: `imap.fastmail.com`, Port: `993`.
- **iCloud Mail**:
  - <https://account.apple.com> → Sign-In & Security → App-Specific Passwords.
  - Host: `imap.mail.me.com`, Port: `993`.
- **Generic / self-hosted**:
  - Use whatever app-password or IMAP credential your provider issues.
  - Find your provider's IMAP host + port (almost always `993` with SSL).

---

## Step 2: Set the environment variables

```bash
export FTT_IMAP_HOST=imap.fastmail.com        # required
export FTT_IMAP_USER=you@fastmail.com         # required
export FTT_IMAP_PASSWORD='your-app-password'  # required (app password!)
# Optional:
export FTT_IMAP_PORT=993        # default 993
export FTT_IMAP_SSL=true        # default true (implicit SSL)
export FTT_IMAP_FOLDER=INBOX    # default INBOX
```

**Env vars always win.** As a convenience, the tracker will also read an
`email.imap` block from `profile.yaml` if present, e.g.:

```yaml
email:
  provider: "imap"
  imap:
    host: "imap.fastmail.com"
    user: "you@fastmail.com"
    # password: "..."   # prefer the env var for secrets
    port: 993
    ssl: true
    folder: "INBOX"
```

Any value set in the environment overrides the profile.

If required config is missing, `--sync` / `--summary` fail with a clear message
pointing back here — no raw traceback.

---

## Step 3: Sync

```bash
# From the repo root
python3 mcp-servers/imap-server/imap_tracker.py --sync            # sync + summary
python3 mcp-servers/imap-server/imap_tracker.py --summary --days 14
python3 mcp-servers/imap-server/imap_tracker.py --raw --days 7    # JSON dump, no DB write
```

Flags:

| Flag        | Meaning                                       |
| ----------- | --------------------------------------------- |
| `--sync`    | Fetch, classify, upsert to DB, print summary  |
| `--summary` | Alias of `--sync`                             |
| `--raw`     | Print parsed emails as JSON (no DB write)     |
| `--days N`  | Look back N days (default 30)                 |
| `--max N`   | Cap at N messages (default 50)                |
| `--mcp`     | Run as a stdio MCP server (see below)         |

> Note: the pipeline's `applications` table is created by
> `src/job_automation.py`. The `email_interactions` table has no schema file in
> this repo yet; until one is shipped, applications still upsert correctly and
> interaction logging is skipped gracefully. Run
> `python3 src/job_cli.py dashboard` once to initialize the core tables if you
> have not already.

---

## Step 4 (optional): Wire it as an MCP server

The `--mcp` flag starts a stdio [Model Context Protocol](https://modelcontextprotocol.io)
server exposing the tracker as tools:

- `sync_imap_to_tracker(days=30, max_results=50)`
- `get_email_summary(days=30, max_results=50)`
- `get_recruiter_emails(days=14, max_results=20)` — read-only

This mode needs the `mcp` package:

```bash
pip install -r mcp-servers/imap-server/requirements.txt   # installs mcp
```

Add to your `.mcp.json` (env carries the IMAP credentials to the server):

```json
{
  "mcpServers": {
    "imap-tracker": {
      "command": "python3",
      "args": ["/path/to/forget-the-thunderdome/mcp-servers/imap-server/imap_tracker.py", "--mcp"],
      "env": {
        "FTT_IMAP_HOST": "imap.fastmail.com",
        "FTT_IMAP_USER": "you@fastmail.com",
        "FTT_IMAP_PASSWORD": "your-app-password"
      }
    }
  }
}
```

The CLI works fine **without** `mcp` installed; the package is only needed for
`--mcp`.

---

## How classification works

Each message is scored by `classify.py::classify_email(subject, sender, body)`,
which mirrors the Gmail provider's keyword rules so every provider yields the
same `email_type` values. Because it is a standalone module, you can unit-test
it directly:

```bash
cd mcp-servers/imap-server
python3 -c "from classify import classify_email; \
print(classify_email('Interview invitation for Senior Engineer','recruiter@acme.com','We would love to schedule a call'), \
classify_email('Update on your application','no-reply@acme.com','Unfortunately we will not be moving forward'))"
# -> interview_invite rejection
```

Edit the keyword lists at the top of `classify.py` to tune matching for your
inbox.

---

## Troubleshooting

- **`IMAP is not configured. Missing: ...`** — set the `FTT_IMAP_*` env vars
  from Step 2.
- **`IMAP login failed`** — use an **app password**, not your account
  password; confirm the user is the full email address.
- **`Could not open folder`** — set `FTT_IMAP_FOLDER` to a mailbox that exists
  (case-sensitive on some servers; try `INBOX`).
- **Nothing found** — widen `--days`, or check the folder actually contains
  recruiter mail.

---

## Privacy

- Credentials live only in your shell environment (or profile.yaml) — nothing
  is transmitted anywhere except your IMAP server.
- The mailbox is opened **read-only** (`SELECT ... readonly=True`); the tool
  never deletes, moves, or marks mail.
- Only parsed fields (company, role, next steps, salary, sender, subject, date)
  are written to the local SQLite DB.
