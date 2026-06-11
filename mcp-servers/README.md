# Gmail Job Tracker MCP Server

Automatically monitors your Gmail for recruiter emails and syncs them to your job_tracker database.

---

## What It Does

1. **Monitors Gmail** — Watches for emails from recruiters, LinkedIn, companies
2. **Parses emails** — Extracts company, role, salary, next steps
3. **Syncs to database** — Auto-logs to job_tracker, updates application status
4. **Provides insights** — Shows recruiter activity, next steps, compensation trends

---

## Quick Setup

```bash
# Run the automated setup (from the repo root)
bash mcp-servers/setup.sh
```

This will:
1. Check for Gmail credentials (and guide you through setup if missing)
2. Add email_interactions table to job_tracker
3. Test Gmail connection
4. You're ready to sync

---

## First Time: Get Gmail Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project: `job-tracker-gmail`
3. Enable Gmail API
4. Create OAuth 2.0 Desktop Credentials
5. Download JSON → `~/.mcp/config/gmail_credentials.json`

Full instructions: See [docs/providers/gmail-setup.md](../docs/providers/gmail-setup.md)

---

## Usage

**Sync recruiter emails to tracker:**
```bash
python3 mcp-servers/gmail-server/gmail_tracker.py --sync
```

**Get email summary:**
```bash
python3 mcp-servers/gmail-server/gmail_tracker.py --summary
```

**View synced emails in database:**
```bash
sqlite3 data/job_tracker.db \
  "SELECT company, email_from, email_date, parsed_next_steps FROM email_history ORDER BY email_date DESC;"
```

---

## What Gets Tracked

| Data | Source | Stored In |
|------|--------|-----------|
| Company name | Email subject/body | `email_interactions.parsed_company` |
| Role title | Email subject/body | `email_interactions.parsed_role` |
| Next steps | Email body (action items) | `email_interactions.parsed_next_steps` |
| Salary range | Email body | `email_interactions.parsed_salary` |
| Email date | Gmail metadata | `email_interactions.email_date` |
| Sender | Gmail metadata | `email_interactions.email_from` |

---

## Email Recognition

Server automatically recognizes emails from:
- `recruiter@*` — Recruiters
- `careers@*` — Company careers teams
- `noreply@linkedin.com` — LinkedIn notifications
- `jobs@*` — Job posting services
- `hiring@*` — Company hiring leads

Add more patterns in `gmail_tracker.py` line 197 if needed.

---

## Daily Automation (Optional)

Run sync automatically every morning at 9am:

```bash
# Add to crontab
crontab -e

# Add this line (replace /path/to/forget-the-thunderdome with your clone):
0 9 * * * cd /path/to/forget-the-thunderdome && python3 mcp-servers/gmail-server/gmail_tracker.py --sync >> data/gmail_sync.log 2>&1
```

---

## Database Schema

Three related tables:

**applications** — Your job applications
```
id | company | role | date_applied | status | ...
```

**email_interactions** — Each recruiter email
```
id | application_id | email_from | email_subject | email_date | parsed_next_steps | parsed_salary | ...
```

**email_history** — View combining both (easiest to query)
```sql
SELECT company, email_from, email_date, parsed_next_steps FROM email_history;
```

---

## Queries

**See all recruiter activity:**
```bash
sqlite3 job_tracker.db "SELECT * FROM email_history ORDER BY email_date DESC LIMIT 20;"
```

**Find which companies mentioned salary:**
```bash
sqlite3 job_tracker.db "SELECT DISTINCT company, parsed_salary FROM email_history WHERE parsed_salary IS NOT NULL;"
```

**Track next steps by company:**
```bash
sqlite3 job_tracker.db "SELECT company, email_date, parsed_next_steps FROM email_history WHERE parsed_next_steps IS NOT NULL ORDER BY email_date DESC;"
```

**See applications created from email contacts:**
```bash
sqlite3 job_tracker.db "SELECT DISTINCT a.company, COUNT(ei.id) as emails FROM applications a LEFT JOIN email_interactions ei ON a.id = ei.application_id GROUP BY a.company;"
```

---

## Privacy & Security

✅ Token stored locally, read-only access, never send/delete emails
✅ You can revoke access anytime in Google Account settings
✅ No full email body stored (only parsed fields)
✅ OAuth 2.0 (never stores your password)

---

## Troubleshooting

**Gmail module not found:**
```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

**Credentials error:**
- Ensure: `~/.mcp/config/gmail_credentials.json` exists
- Regenerate from Google Cloud Console if needed

**Emails not syncing:**
- Check: `gmail_tracker.py` line ~90 (email search filters)
- Add more sender patterns if recruiters use different addresses

---

## Next Steps

1. ✅ Set up Gmail credentials
2. ✅ Run `bash mcp-servers/setup.sh`
3. ✅ Sync emails: `python3 mcp-servers/gmail-server/gmail_tracker.py --sync`
4. ✅ View in database: `sqlite3 data/job_tracker.db "SELECT * FROM email_history;"`
5. ✅ Update job applications as emails come in

Your recruiter activity is now being tracked automatically!
