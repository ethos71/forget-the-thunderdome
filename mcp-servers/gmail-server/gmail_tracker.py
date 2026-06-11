#!/usr/bin/env python3
"""
Gmail Job Tracker MCP Server
Monitors Gmail for recruiter emails, job opportunities, and application updates.
Syncs to the job_tracker database. Run standalone: python3 gmail_tracker.py --sync

Tip: run inside a virtualenv with up-to-date google-auth (older system
versions can fail to load cached pickled tokens).
"""

import os
import sys
import json
import re
import sqlite3
import argparse
import base64
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Make src/profile_loader importable from this MCP server directory
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from profile_loader import load_profile, default_db_path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# ─── Constants ────────────────────────────────────────────────────────────────

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar.readonly',
]
TOKEN_PATH    = os.path.expanduser('~/.mcp/config/gmail_token.pickle')
CREDS_PATH    = os.path.expanduser('~/.mcp/config/gmail_credentials.json')
# DB lives at <repo_root>/data/job_tracker.db (data/ is created if missing)
DB_PATH       = default_db_path()


def _known_companies() -> list:
    """Company names recognized in recruiter emails.

    Sourced from the profile: search.target_companies plus the companies in
    narrative.work_history. Add more target_companies to profile.yaml to
    improve matching.
    """
    profile = load_profile()
    companies = [c.lower() for c in profile.get('search', {}).get('target_companies', [])]
    for job in profile.get('narrative', {}).get('work_history', []):
        name = (job.get('company') or '').lower()
        if name and name not in companies:
            companies.append(name)
    return companies


_KNOWN_COMPANIES_CACHE = None


def get_known_companies() -> list:
    """Lazily load + cache the known-companies list from the profile."""
    global _KNOWN_COMPANIES_CACHE
    if _KNOWN_COMPANIES_CACHE is None:
        _KNOWN_COMPANIES_CACHE = _known_companies()
    return _KNOWN_COMPANIES_CACHE

# Gmail search query: catches recruiter outreach, job applications, interview invites
RECRUITER_QUERY = (
    '('
    'subject:"interview" OR subject:"opportunity" OR subject:"job" OR '
    'subject:"position" OR subject:"applied" OR subject:"application" OR '
    'subject:"hiring" OR subject:"recruiter" OR subject:"recruiting" OR '
    'subject:"phone screen" OR subject:"technical screen" OR '
    'subject:"offer" OR subject:"next steps" OR subject:"follow up" OR '
    'from:ashbyhq.com OR from:greenhouse.io OR from:lever.co OR '
    'from:workday.com OR from:myworkday.com OR from:taleo.net OR '
    'from:icims.com OR from:smartrecruiters.com OR from:bamboohr.com OR '
    'from:jobvite.com OR from:workable.com OR from:recruiters OR '
    'from:talent OR from:careers OR from:hiring OR from:hr'
    ')'
)

# ─── Auth + DB ────────────────────────────────────────────────────────────────

def authenticate_gmail():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as f:
            creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            # Token revoked — delete and force re-auth
            os.remove(TOKEN_PATH)
            creds = None
    if not creds or not creds.valid:
        if not os.path.exists(CREDS_PATH):
            raise FileNotFoundError(
                f"Gmail credentials not found at {CREDS_PATH}.\n"
                "See docs/providers/gmail-setup.md to create them."
            )
        flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
        creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, 'wb') as f:
            pickle.dump(creds, f)
    return build('gmail', 'v1', credentials=creds)


def get_db():
    # TODO(ftt): the applications table is created by src/job_automation.py
    # (JobSearchDB.init_db). The email_interactions table has no schema file in
    # this repo yet — create it here or ship an email_schema.sql. Until then,
    # run `python3 src/job_cli.py dashboard` once to initialize the core tables.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─── Parsing Helpers ──────────────────────────────────────────────────────────

def extract_body(msg: dict) -> str:
    try:
        payload = msg['payload']
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
            # Fallback: try HTML part
            for part in payload['parts']:
                if part['mimeType'] == 'text/html' and 'data' in part.get('body', {}):
                    text = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                    return re.sub(r'<[^>]+>', ' ', text)
        elif 'data' in payload.get('body', {}):
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')
    except Exception:
        pass
    return ''


def extract_company(subject: str, body: str, sender: str) -> Optional[str]:
    text = f"{subject} {body} {sender}".lower()
    for company in get_known_companies():
        if company in text:
            return company.title()
    # Try to extract from sender domain
    domain_match = re.search(r'@([\w-]+)\.(com|io|ai|co)', sender.lower())
    if domain_match:
        domain = domain_match.group(1)
        if domain not in ('gmail', 'yahoo', 'hotmail', 'outlook', 'icloud', 'protonmail'):
            return domain.replace('-', ' ').title()
    return None


def extract_role(subject: str, body: str) -> Optional[str]:
    role_patterns = [
        r'(?:principal|staff|senior|lead|sr\.?)\s+(?:software|platform|ai|ml|data|backend|fullstack)?\s*(?:engineer|architect|developer|scientist)',
        r'(?:head|director|vp)\s+of\s+engineering',
        r'software engineer(?:\s+(?:iii|iv|v|3|4|5))?',
        r'(?:principal|staff)\s+engineer',
        r'engineering manager',
    ]
    text = f"{subject} {body[:500]}"
    for pat in role_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip().title()
    return None


def extract_salary(body: str) -> Optional[str]:
    patterns = [
        r'\$\s*(\d{2,3}(?:,\d{3})?)\s*(?:k|K)?\s*[-–]\s*\$?\s*(\d{2,3}(?:,\d{3})?)\s*(?:k|K)?',
        r'\$\s*(\d{2,3}(?:,\d{3})?)\s*(?:k|K)',
        r'(\d{2,3})k?\s*[-–]\s*(\d{2,3})k?\s*(?:per year|\/yr|annually)',
    ]
    for pat in patterns:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def extract_next_steps(body: str) -> Optional[str]:
    step_keywords = ['schedule', 'next step', 'phone screen', 'technical interview',
                     'please reply', 'let me know', 'available', 'calendly', 'calendar',
                     'click here to', 'book a time', 'follow up', 'reach out']
    lines = body.split('\n')
    for line in lines:
        clean = line.strip()
        if len(clean) > 10 and any(kw in clean.lower() for kw in step_keywords):
            return clean[:200]
    return None


def classify_email(subject: str, body: str) -> str:
    """Classify email type: recruiter_outreach, application_update, interview_invite, rejection, offer, other"""
    text = f"{subject} {body[:300]}".lower()
    if any(w in text for w in ['unfortunately', 'not moving forward', 'decided to move on',
                                'not a fit', 'other candidates', 'position has been filled']):
        return 'rejection'
    if any(w in text for w in ['offer', 'pleased to offer', 'compensation package', 'start date']):
        return 'offer'
    if any(w in text for w in ['interview', 'phone screen', 'technical screen', 'meet with', 'schedule time']):
        return 'interview_invite'
    if any(w in text for w in ['received your application', 'application confirmed', 'thank you for applying',
                                'we have received']):
        return 'application_update'
    if any(w in text for w in ['opportunity', 'exciting role', 'came across your profile',
                                'thought you might be', 'open to hearing', 'are you interested']):
        return 'recruiter_outreach'
    return 'other'


# ─── Core Tracker ─────────────────────────────────────────────────────────────

class GmailJobTracker:
    def __init__(self):
        self.service = authenticate_gmail()
        self.db = get_db()

    def fetch_emails(self, days_back: int = 30, max_results: int = 50) -> list:
        query = f"{RECRUITER_QUERY} newer_than:{days_back}d"
        try:
            result = self.service.users().messages().list(
                userId='me', q=query, maxResults=max_results
            ).execute()
            messages = result.get('messages', [])
        except HttpError as e:
            print(f"Gmail API error: {e}")
            return []

        emails = []
        for m in messages:
            try:
                msg = self.service.users().messages().get(
                    userId='me', id=m['id'], format='full'
                ).execute()
                headers = {h['name']: h['value'] for h in msg['payload']['headers']}
                body = extract_body(msg)
                subject = headers.get('Subject', '')
                sender  = headers.get('From', '')
                date    = headers.get('Date', '')
                emails.append({
                    'id': m['id'],
                    'subject': subject,
                    'sender': sender,
                    'date': date,
                    'snippet': msg.get('snippet', ''),
                    'body': body,
                    'company': extract_company(subject, body, sender),
                    'role': extract_role(subject, body),
                    'salary': extract_salary(body),
                    'next_steps': extract_next_steps(body),
                    'email_type': classify_email(subject, body),
                })
            except Exception as e:
                print(f"Error reading message {m['id']}: {e}")
        return emails

    def sync_to_db(self, days_back: int = 30) -> dict:
        emails = self.fetch_emails(days_back=days_back)
        summary = {
            'total': len(emails),
            'logged': 0,
            'by_type': {},
            'companies': [],
            'interviews': [],
            'rejections': [],
            'offers': [],
        }

        cursor = self.db.cursor()
        for email in emails:
            etype = email['email_type']
            summary['by_type'][etype] = summary['by_type'].get(etype, 0) + 1

            if etype == 'interview_invite' and email['company']:
                summary['interviews'].append({'company': email['company'], 'role': email['role'], 'date': email['date']})
            if etype == 'rejection' and email['company']:
                summary['rejections'].append({'company': email['company'], 'date': email['date']})
            if etype == 'offer' and email['company']:
                summary['offers'].append({'company': email['company'], 'role': email['role'], 'date': email['date']})

            if not email.get('company'):
                continue

            company = email['company']
            if company not in summary['companies']:
                summary['companies'].append(company)

            # Upsert application
            cursor.execute(
                'SELECT id, status FROM applications WHERE company = ? AND role = ?',
                (company, email['role'] or 'Unspecified Role')
            )
            row = cursor.fetchone()
            status_map = {
                'interview_invite': 'interview',
                'offer': 'offer',
                'rejection': 'rejected',
                'recruiter_outreach': 'contacted',
                'application_update': 'applied',
            }
            new_status = status_map.get(etype, 'contacted')

            if row:
                app_id = row['id']
                # Only promote status, never demote
                status_order = ['applied', 'contacted', 'interview', 'offer', 'rejected']
                current_idx = status_order.index(row['status']) if row['status'] in status_order else 0
                new_idx = status_order.index(new_status) if new_status in status_order else 0
                if new_idx > current_idx:
                    cursor.execute('UPDATE applications SET status = ? WHERE id = ?', (new_status, app_id))
            else:
                cursor.execute(
                    'INSERT INTO applications (company, role, date_applied, status, notes) VALUES (?, ?, ?, ?, ?)',
                    (company, email['role'] or 'Unspecified Role',
                     datetime.now().date(), new_status,
                     f"Auto-logged from email: {email['sender']}")
                )
                app_id = cursor.lastrowid

            # Log email interaction (skip duplicates by message id)
            try:
                cursor.execute(
                    '''INSERT OR IGNORE INTO email_interactions
                       (application_id, email_from, email_subject, email_date, parsed_next_steps, parsed_salary)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (app_id, email['sender'], email['subject'],
                     email['date'], email['next_steps'], email['salary'])
                )
                summary['logged'] += 1
            except sqlite3.OperationalError:
                # email_interactions table may not exist yet; try without unique constraint
                cursor.execute(
                    '''INSERT INTO email_interactions
                       (application_id, email_from, email_subject, email_date, parsed_next_steps, parsed_salary)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (app_id, email['sender'], email['subject'],
                     email['date'], email['next_steps'], email['salary'])
                )
                summary['logged'] += 1

        self.db.commit()
        return summary

    def print_summary(self, days_back: int = 30):
        summary = self.sync_to_db(days_back=days_back)
        print(f"\n{'='*60}")
        print(f"  Gmail Job Tracker — Past {days_back} Days")
        print(f"{'='*60}")
        print(f"  Total emails scanned : {summary['total']}")
        print(f"  Logged to DB         : {summary['logged']}")
        print()
        print(f"  By type:")
        for etype, count in summary['by_type'].items():
            print(f"    {etype:<25} {count}")
        print()
        if summary['interviews']:
            print(f"  INTERVIEWS ({len(summary['interviews'])}):")
            for i in summary['interviews']:
                print(f"    ✓ {i['company']} — {i['role'] or 'unspecified'}")
        if summary['offers']:
            print(f"  OFFERS ({len(summary['offers'])}):")
            for o in summary['offers']:
                print(f"    ★ {o['company']} — {o['role'] or 'unspecified'}")
        if summary['rejections']:
            print(f"  Rejections: {', '.join(r['company'] for r in summary['rejections'])}")
        if summary['companies']:
            print(f"\n  Companies active: {', '.join(summary['companies'])}")
        print()

    def get_raw_emails(self, days_back: int = 14, max_results: int = 20) -> list:
        """Return raw parsed emails for inspection (no DB write)."""
        return self.fetch_emails(days_back=days_back, max_results=max_results)


# ─── MCP Server ───────────────────────────────────────────────────────────────

if MCP_AVAILABLE:
    server = Server("gmail-job-tracker")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(name="get_recruiter_emails",     description="Fetch recruiter/job emails from past N days (read-only, no DB write)",
                 inputSchema={"type": "object", "properties": {"days_back": {"type": "integer", "default": 14}}}),
            Tool(name="sync_gmail_to_tracker",    description="Sync Gmail job emails to job_tracker database",
                 inputSchema={"type": "object", "properties": {"days_back": {"type": "integer", "default": 30}}}),
            Tool(name="get_email_summary",        description="Print a structured summary of job emails: interviews, offers, rejections, companies",
                 inputSchema={"type": "object", "properties": {"days_back": {"type": "integer", "default": 30}}}),
            Tool(name="get_interview_pipeline",   description="Return only interview invites and offers from recent emails",
                 inputSchema={"type": "object", "properties": {"days_back": {"type": "integer", "default": 60}}}),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        tracker = GmailJobTracker()
        days_back = arguments.get('days_back', 30)

        if name == "get_recruiter_emails":
            emails = tracker.get_raw_emails(days_back=days_back)
            # Strip full body to save context
            for e in emails:
                e['body'] = e['body'][:400] if e['body'] else ''
            return [TextContent(type="text", text=json.dumps(emails, indent=2, default=str))]

        elif name == "sync_gmail_to_tracker":
            summary = tracker.sync_to_db(days_back=days_back)
            return [TextContent(type="text", text=json.dumps(summary, indent=2, default=str))]

        elif name == "get_email_summary":
            summary = tracker.sync_to_db(days_back=days_back)
            lines = [
                f"Gmail Summary — Past {days_back} Days",
                f"Total emails: {summary['total']}  |  Logged: {summary['logged']}",
                "",
                "By type: " + ", ".join(f"{k}={v}" for k, v in summary['by_type'].items()),
            ]
            if summary['interviews']:
                lines.append(f"\nINTERVIEWS ({len(summary['interviews'])}):")
                lines += [f"  • {i['company']} — {i['role']}" for i in summary['interviews']]
            if summary['offers']:
                lines.append(f"\nOFFERS ({len(summary['offers'])}):")
                lines += [f"  • {o['company']} — {o['role']}" for o in summary['offers']]
            if summary['rejections']:
                lines.append(f"\nRejections: {', '.join(r['company'] for r in summary['rejections'])}")
            lines.append(f"\nActive companies: {', '.join(summary['companies'])}")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "get_interview_pipeline":
            emails = tracker.fetch_emails(days_back=days_back)
            pipeline = [e for e in emails if e['email_type'] in ('interview_invite', 'offer')]
            return [TextContent(type="text", text=json.dumps(pipeline, indent=2, default=str))]

        return [TextContent(type="text", text="Unknown tool")]


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Gmail Job Tracker')
    parser.add_argument('--sync',    action='store_true', help='Sync emails to DB and print summary')
    parser.add_argument('--summary', action='store_true', help='Print summary without DB write')
    parser.add_argument('--raw',     action='store_true', help='Dump raw parsed emails as JSON')
    parser.add_argument('--days',    type=int, default=30, help='Days back to search (default: 30)')
    parser.add_argument('--max',     type=int, default=50, help='Max emails to fetch (default: 50)')
    args = parser.parse_args()

    tracker = GmailJobTracker()

    if args.raw:
        emails = tracker.get_raw_emails(days_back=args.days, max_results=args.max)
        for e in emails:
            e['body'] = e['body'][:300]
        print(json.dumps(emails, indent=2, default=str))
    elif args.sync or args.summary:
        tracker.print_summary(days_back=args.days)
    else:
        print("Gmail Job Tracker ready.")
        print("Usage:")
        print("  python3 gmail_tracker.py --sync          # sync to DB + print summary")
        print("  python3 gmail_tracker.py --raw --days 14 # dump raw emails as JSON")
        print("  python3 gmail_tracker.py --summary       # summary only")
