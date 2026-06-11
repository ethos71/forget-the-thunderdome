# Gmail MCP Server Setup

Complete setup guide for connecting your Gmail to the job tracker.

---

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project:
   - Click "Select a Project" → "New Project"
   - Name: `job-tracker-gmail`
   - Click Create

3. Enable Gmail API:
   - Search for "Gmail API"
   - Click "Gmail API"
   - Click "Enable"

---

## Step 2: Create OAuth 2.0 Credentials

1. Go to "Credentials" in left sidebar
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted: Click "Configure OAuth consent screen first"
   - User Type: External
   - Fill in App Name: `Job Tracker Gmail Sync`
   - Your email: `your-email@example.com` (use your own Gmail address)
   - Add yourself as a test user
   - Save and Continue

4. Back to Credentials → Create OAuth client ID
   - Application type: **Desktop application**
   - Name: `Job Tracker`
   - Click Create

5. Download JSON:
   - Click the download icon
   - Save as `gmail_credentials.json`

6. Copy to your job folder:
   ```bash
   cp ~/Downloads/gmail_credentials.json ~/.mcp/config/gmail_credentials.json
   ```

---

## Step 3: Install Dependencies

```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

---

## Step 4: First Run (OAuth Authorization)

```bash
# From the repo root
python3 mcp-servers/gmail-server/gmail_tracker.py
```

First time will:
1. Open a browser window
2. Ask you to authorize "Job Tracker" to access Gmail
3. Click "Allow"
4. Save token locally (never expires unless you revoke)

---

## Step 5: Update Your Database

Add email tracking to your job_tracker database (at `data/job_tracker.db`):

```bash
# TODO(ftt): an email_schema.sql (email_interactions table + email_history view)
# is not shipped in this repo yet — see mcp-servers/setup.sh for details.
sqlite3 data/job_tracker.db < mcp-servers/gmail-server/email_schema.sql
```

---

## Step 6: Sync Your Emails

```bash
python3 mcp-servers/gmail-server/gmail_tracker.py --sync
```

This will:
1. Fetch recruiter emails from past 7 days
2. Parse company, role, next steps, salary
3. Create/update applications in job_tracker
4. Log email interactions

---

## Queries to View Synced Emails

```bash
# View all email interactions by application
sqlite3 job_tracker.db "SELECT company, email_from, email_date, parsed_next_steps FROM email_history ORDER BY email_date DESC;"

# See which companies emailed you
sqlite3 job_tracker.db "SELECT DISTINCT email_from FROM email_interactions ORDER BY email_from;"

# Check if salary was mentioned in any email
sqlite3 job_tracker.db "SELECT company, parsed_salary FROM email_history WHERE parsed_salary IS NOT NULL;"
```

---

## MCP Integration (Optional)

To use this as an MCP server with other tools:

1. Add to your `.mcp.json`:
```json
{
  "mcpServers": {
    "gmail-tracker": {
      "command": "python3",
      "args": ["/path/to/forget-the-thunderdome/mcp-servers/gmail-server/gmail_tracker.py"]
    }
  }
}
```

2. Then tools can call:
   - `get_recruiter_emails()` — Fetch unread recruiter emails
   - `sync_gmail_to_tracker()` — Auto-sync to job_tracker
   - `get_email_summary()` — Summary of recent recruiter activity

---

## What Gets Parsed from Emails

**From Subject & Body:**
- Company name (matches known list)
- Role title (looks for role keywords)
- Next steps / Call to action
- Salary range (if mentioned)

**Stored in Database:**
- Email sender
- Email subject
- Email date
- Parsed information
- Application ID (matched by company/role)

**Example**:
```
Email from: recruiter@examplecorp.com
Subject: Exciting Opportunity - Sr. Backend Engineer

Parsed:
- Company: Example Corp
- Role: Sr. Backend Engineer
- Next Steps: "Schedule a phone screen for next week"
- Salary: "$150k-$175k"

Logged to: applications (id=8) + email_interactions
```

---

## Troubleshooting

**Q: "Module not found" error**
```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

**Q: OAuth won't open browser**
```bash
# Manual auth flow (copy link to browser):
python3 gmail_tracker.py --manual
```

**Q: Gmail credentials error**
- Check: `~/.mcp/config/gmail_credentials.json` exists
- If missing: Repeat Step 2 (download from Cloud Console)

**Q: Can't find emails**
- Check: Gmail search filters in `gmail_tracker.py` (line ~90)
- Add more sender patterns if needed

**Q: Salary not being extracted**
- Check: Email has salary written in format like "$200k" or "$200,000"
- Regex pattern is in `_extract_salary()` method

---

## Privacy & Security

✅ **What's secure:**
- Token is stored locally (never sent anywhere)
- Gmail API is read-only (we only read, never send/delete)
- Credentials are your OAuth token, not your password
- You can revoke access anytime in Google Account settings

✅ **What's stored:**
- Only parsed information (company, role, next steps)
- Email sender, subject, date
- No full email body (unless you enable it in config)

---

## Automation (Optional)

To sync Gmail daily automatically:

**Create cron job** (runs daily at 9am — replace the path with your clone):
```bash
0 9 * * * cd /path/to/forget-the-thunderdome && python3 mcp-servers/gmail-server/gmail_tracker.py --sync >> data/gmail_sync.log 2>&1
```

Add to crontab:
```bash
crontab -e
# Paste the line above, save
```

---

All set! Your Gmail is now connected to your job tracker. Emails from recruiters will automatically appear in your database.
