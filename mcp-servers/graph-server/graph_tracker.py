#!/usr/bin/env python3
"""
Microsoft 365 / Outlook (Microsoft Graph) Job Tracker — SCAFFOLD.

    ┌─────────────────────────────────────────────────────────────────────┐
    │ HONEST STATUS: this provider is a fully-structured SCAFFOLD, not a   │
    │ verified integration. It mirrors the Gmail/IMAP servers' shape and   │
    │ the Graph API calls are written out correctly, BUT it cannot be run  │
    │ to completion in this repo because it needs (a) an Azure app         │
    │ registration (client id + tenant) and (b) the `msal` and `requests`  │
    │ packages, which are NOT installed here. With those in place it       │
    │ should work; treat it as unverified until you exercise it yourself.  │
    │ See docs/providers/microsoft-graph-setup.md.                         │
    └─────────────────────────────────────────────────────────────────────┘

Auth uses MSAL's device-code flow (the friendliest for a local CLI): you run
the command, it prints a short code + URL, you approve in a browser, and it
caches a token. Mail is read via Microsoft Graph `/me/messages`.

`msal` and `requests` are imported LAZILY inside the auth/fetch path so this
module imports cleanly and `--help` works even though neither is installed.

Config from environment:
    FTT_GRAPH_CLIENT_ID   (required)  the Azure app (client) id
    FTT_GRAPH_TENANT_ID   (default 'common')
    FTT_GRAPH_SCOPES      (default 'Mail.Read')  space-separated

Standalone:
    python3 graph_tracker.py --sync
    python3 graph_tracker.py --summary --days 14
    python3 graph_tracker.py --mcp        # run as an MCP stdio server
"""

import os
import sys
import json
import re
import sqlite3
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Make src/ (profile_loader, job_automation) importable from this dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from profile_loader import load_profile, default_db_path  # noqa: E402

# Reuse the IMAP provider's unit-tested classifier via a path shim. If that
# import fails for any reason, fall back to a small inline duplicate so this
# module never hard-depends on a sibling directory.
# NOTE(future refactor): the ideal home for classify_email is a shared src/
# module every provider imports; until then we reuse IMAP's copy here.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'imap-server'))
try:
    from classify import classify_email  # noqa: E402
except Exception:  # pragma: no cover - defensive duplicate
    def classify_email(subject, sender, body):
        text = f"{subject or ''} {(body or '')[:300]}".lower()
        if any(w in text for w in ['unfortunately', 'not moving forward',
                                   'not a fit', 'other candidates',
                                   'position has been filled', 'regret to inform']):
            return 'rejection'
        if any(w in text for w in ['offer', 'pleased to offer',
                                   'compensation package', 'start date']):
            return 'offer'
        if any(w in text for w in ['interview', 'phone screen',
                                   'technical screen', 'meet with', 'schedule time']):
            return 'interview_invite'
        if any(w in text for w in ['received your application',
                                   'application confirmed', 'thank you for applying',
                                   'we have received']):
            return 'application_update'
        if any(w in text for w in ['opportunity', 'exciting role',
                                   'came across your profile', 'are you interested']):
            return 'recruiter_outreach'
        return 'other'

# NOTE: `msal` and `requests` are imported LAZILY inside GraphTracker so this
# module imports and `--help` works even though neither package is installed.

DOC_HINT = "docs/providers/microsoft-graph-setup.md"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_CACHE_PATH = os.path.expanduser('~/.mcp/config/graph_token_cache.json')


class GraphConfigError(RuntimeError):
    """Raised when Graph config/deps are missing. Caught for a clean message."""


# ─── Config ───────────────────────────────────────────────────────────────────

def load_graph_config() -> dict:
    """Resolve Graph config from env (with a profile.yaml fallback for tenant).

    Raises GraphConfigError with full setup instructions if FTT_GRAPH_CLIENT_ID
    is missing.
    """
    client_id = os.environ.get('FTT_GRAPH_CLIENT_ID')
    tenant_id = os.environ.get('FTT_GRAPH_TENANT_ID', 'common')
    scopes = os.environ.get('FTT_GRAPH_SCOPES', 'Mail.Read').split()

    if not client_id:
        raise GraphConfigError(_setup_instructions())

    return {'client_id': client_id, 'tenant_id': tenant_id, 'scopes': scopes}


def _setup_instructions(missing_dep: Optional[str] = None) -> str:
    lines = []
    if missing_dep:
        lines.append(
            f"Microsoft Graph support needs the '{missing_dep}' package "
            "(not installed).")
        lines.append("    pip install msal requests")
        lines.append("")
    lines.append("Microsoft 365 / Outlook (Graph) is not configured. To use it:")
    lines.append("")
    lines.append("  1. Register an app in Azure (Entra ID) > App registrations:")
    lines.append("       - Supported account types: your choice (personal + work).")
    lines.append("       - Add the DELEGATED Microsoft Graph permission: Mail.Read")
    lines.append("       - Enable 'Allow public client flows' (for device-code auth).")
    lines.append("  2. Copy the Application (client) ID and set env vars:")
    lines.append("       export FTT_GRAPH_CLIENT_ID=<application-client-id>")
    lines.append("       export FTT_GRAPH_TENANT_ID=common   # or your tenant id")
    lines.append("       export FTT_GRAPH_SCOPES='Mail.Read'  # optional")
    lines.append("  3. Install deps:  pip install msal requests")
    lines.append("  4. Run again; approve the device code shown in your browser.")
    lines.append("")
    lines.append(f"Full walkthrough: {DOC_HINT}")
    return "\n".join(lines)


# ─── Extraction helpers (mirror the Gmail/IMAP reference helpers) ─────────────
# NOTE(future refactor): duplicated from the IMAP provider for the same reason
# classify_email is reused — a shared src/ module could unify these later.

_KNOWN_COMPANIES_CACHE = None


def get_known_companies() -> list:
    global _KNOWN_COMPANIES_CACHE
    if _KNOWN_COMPANIES_CACHE is None:
        try:
            profile = load_profile()
        except Exception:
            _KNOWN_COMPANIES_CACHE = []
            return _KNOWN_COMPANIES_CACHE
        companies = [c.lower() for c in
                     profile.get('search', {}).get('target_companies', [])]
        for job in profile.get('narrative', {}).get('work_history', []):
            name = (job.get('company') or '').lower()
            if name and name not in companies:
                companies.append(name)
        _KNOWN_COMPANIES_CACHE = companies
    return _KNOWN_COMPANIES_CACHE


def extract_company(subject: str, body: str, sender: str) -> Optional[str]:
    text = f"{subject} {body} {sender}".lower()
    for company in get_known_companies():
        if company in text:
            return company.title()
    domain_match = re.search(r'@([\w-]+)\.(com|io|ai|co)', sender.lower())
    if domain_match:
        domain = domain_match.group(1)
        if domain not in ('gmail', 'yahoo', 'hotmail', 'outlook', 'icloud',
                          'protonmail', 'live', 'msn'):
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
    for line in body.split('\n'):
        clean = line.strip()
        if len(clean) > 10 and any(kw in clean.lower() for kw in step_keywords):
            return clean[:200]
    return None


def _strip_html(html: str) -> str:
    return re.sub(r'<[^>]+>', ' ', html or '')


def get_db():
    conn = sqlite3.connect(default_db_path())
    conn.row_factory = sqlite3.Row
    return conn


# ─── Core Tracker ─────────────────────────────────────────────────────────────

class GraphTracker:
    """Microsoft Graph-backed job email tracker (scaffold).

    Construction validates config only. `msal`/`requests` are imported lazily
    inside _get_token()/fetch_emails so importing this module (and --help) works
    without those packages.
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_graph_config()

    # ---- auth -------------------------------------------------------------
    def _get_token(self) -> str:
        try:
            import msal
        except ImportError as e:
            raise GraphConfigError(_setup_instructions('msal')) from e

        cfg = self.config
        authority = f"https://login.microsoftonline.com/{cfg['tenant_id']}"

        cache = msal.SerializableTokenCache()
        if os.path.exists(TOKEN_CACHE_PATH):
            try:
                with open(TOKEN_CACHE_PATH, 'r', encoding='utf-8') as f:
                    cache.deserialize(f.read())
            except Exception:
                pass

        app = msal.PublicClientApplication(
            cfg['client_id'], authority=authority, token_cache=cache)

        # Try silent auth from cache first.
        result = None
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(cfg['scopes'], account=accounts[0])

        # Fall back to the device-code flow.
        if not result:
            flow = app.initiate_device_flow(scopes=cfg['scopes'])
            if 'user_code' not in flow:
                raise GraphConfigError(
                    "Failed to start device-code flow. Verify the Azure app "
                    "allows public client flows and the client id is correct.\n"
                    f"See {DOC_HINT}.")
            print(flow['message'], file=sys.stderr)  # instructs the user
            result = app.acquire_token_by_device_flow(flow)

        if not result or 'access_token' not in result:
            err = (result or {}).get('error_description', 'unknown error')
            raise GraphConfigError(f"Microsoft Graph auth failed: {err}\nSee {DOC_HINT}.")

        # Persist the (possibly refreshed) cache.
        if cache.has_state_changed:
            try:
                os.makedirs(os.path.dirname(TOKEN_CACHE_PATH), exist_ok=True)
                with open(TOKEN_CACHE_PATH, 'w', encoding='utf-8') as f:
                    f.write(cache.serialize())
            except Exception:
                pass

        return result['access_token']

    # ---- fetch ------------------------------------------------------------
    def fetch_emails(self, days_back: int = 30, max_results: int = 50) -> list:
        try:
            import requests
        except ImportError as e:
            raise GraphConfigError(_setup_instructions('requests')) from e

        token = self._get_token()
        headers = {'Authorization': f'Bearer {token}'}

        since = (datetime.now(timezone.utc) - timedelta(days=days_back))
        since_iso = since.strftime('%Y-%m-%dT%H:%M:%SZ')
        params = {
            '$filter': f"receivedDateTime ge {since_iso}",
            '$select': 'subject,from,receivedDateTime,bodyPreview,body',
            '$orderby': 'receivedDateTime desc',
            '$top': str(min(max_results, 50)),
        }

        emails = []
        url = f"{GRAPH_BASE}/me/messages"
        while url and len(emails) < max_results:
            resp = requests.get(url, headers=headers,
                                params=params if url.endswith('/messages') else None,
                                timeout=30)
            if resp.status_code != 200:
                raise GraphConfigError(
                    f"Graph API error {resp.status_code}: {resp.text[:300]}\n"
                    f"Check the Mail.Read permission and consent. See {DOC_HINT}.")
            data = resp.json()
            for msg in data.get('value', []):
                subject = msg.get('subject', '') or ''
                from_field = (msg.get('from') or {}).get('emailAddress', {}) or {}
                sender = from_field.get('address', '') or from_field.get('name', '')
                date = msg.get('receivedDateTime', '')
                body_obj = msg.get('body') or {}
                if body_obj.get('contentType') == 'html':
                    body = _strip_html(body_obj.get('content', ''))
                else:
                    body = body_obj.get('content', '') or msg.get('bodyPreview', '')
                emails.append({
                    'id': msg.get('id', ''),
                    'subject': subject,
                    'sender': sender,
                    'date': date,
                    'snippet': msg.get('bodyPreview', ''),
                    'body': body,
                    'company': extract_company(subject, body, sender),
                    'role': extract_role(subject, body),
                    'salary': extract_salary(body),
                    'next_steps': extract_next_steps(body),
                    'email_type': classify_email(subject, sender, body),
                })
                if len(emails) >= max_results:
                    break
            url = data.get('@odata.nextLink')
        return emails

    # ---- sync -------------------------------------------------------------
    def sync_to_db(self, days_back: int = 30, max_results: int = 50) -> dict:
        """Fetch, classify, and upsert into the pipeline DB.

        Returns a summary dict shaped like the Gmail/IMAP servers'.
        """
        emails = self.fetch_emails(days_back=days_back, max_results=max_results)
        summary = {
            'total': len(emails),
            'logged': 0,
            'by_type': {},
            'companies': [],
            'interviews': [],
            'rejections': [],
            'offers': [],
        }

        db = get_db()
        cursor = db.cursor()
        status_map = {
            'interview_invite': 'interview',
            'offer': 'offer',
            'rejection': 'rejected',
            'recruiter_outreach': 'contacted',
            'application_update': 'applied',
        }
        status_order = ['applied', 'contacted', 'interview', 'offer', 'rejected']

        for em in emails:
            etype = em['email_type']
            summary['by_type'][etype] = summary['by_type'].get(etype, 0) + 1

            if etype == 'interview_invite' and em['company']:
                summary['interviews'].append(
                    {'company': em['company'], 'role': em['role'], 'date': em['date']})
            if etype == 'rejection' and em['company']:
                summary['rejections'].append(
                    {'company': em['company'], 'date': em['date']})
            if etype == 'offer' and em['company']:
                summary['offers'].append(
                    {'company': em['company'], 'role': em['role'], 'date': em['date']})

            if not em.get('company'):
                continue

            company = em['company']
            if company not in summary['companies']:
                summary['companies'].append(company)

            role = em['role'] or 'Unspecified Role'
            new_status = status_map.get(etype, 'contacted')

            cursor.execute(
                'SELECT id, status FROM applications WHERE company = ? AND role = ?',
                (company, role))
            row = cursor.fetchone()
            if row:
                app_id = row['id']
                cur_idx = status_order.index(row['status']) if row['status'] in status_order else 0
                new_idx = status_order.index(new_status) if new_status in status_order else 0
                if new_idx > cur_idx:
                    cursor.execute('UPDATE applications SET status = ? WHERE id = ?',
                                   (new_status, app_id))
            else:
                cursor.execute(
                    'INSERT INTO applications (company, role, date_applied, status, notes) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (company, role, datetime.now().date(), new_status,
                     f"Auto-logged from Microsoft Graph email: {em['sender']}"))
                app_id = cursor.lastrowid

            try:
                cursor.execute(
                    'INSERT OR IGNORE INTO email_interactions '
                    '(application_id, email_from, email_subject, email_date, '
                    'parsed_next_steps, parsed_salary) VALUES (?, ?, ?, ?, ?, ?)',
                    (app_id, em['sender'], em['subject'], em['date'],
                     em['next_steps'], em['salary']))
                summary['logged'] += 1
            except sqlite3.OperationalError:
                try:
                    cursor.execute(
                        'INSERT INTO email_interactions '
                        '(application_id, email_from, email_subject, email_date, '
                        'parsed_next_steps, parsed_salary) VALUES (?, ?, ?, ?, ?, ?)',
                        (app_id, em['sender'], em['subject'], em['date'],
                         em['next_steps'], em['salary']))
                    summary['logged'] += 1
                except sqlite3.OperationalError:
                    pass

        db.commit()
        db.close()
        return summary

    def print_summary(self, days_back: int = 30, max_results: int = 50):
        summary = self.sync_to_db(days_back=days_back, max_results=max_results)
        print(f"\n{'=' * 60}")
        print(f"  Microsoft Graph Job Tracker — Past {days_back} Days")
        print(f"{'=' * 60}")
        print(f"  Total emails scanned : {summary['total']}")
        print(f"  Logged to DB         : {summary['logged']}")
        print()
        print("  By type:")
        for etype, count in summary['by_type'].items():
            print(f"    {etype:<25} {count}")
        print()
        if summary['interviews']:
            print(f"  INTERVIEWS ({len(summary['interviews'])}):")
            for i in summary['interviews']:
                print(f"    + {i['company']} — {i['role'] or 'unspecified'}")
        if summary['offers']:
            print(f"  OFFERS ({len(summary['offers'])}):")
            for o in summary['offers']:
                print(f"    * {o['company']} — {o['role'] or 'unspecified'}")
        if summary['rejections']:
            print(f"  Rejections: {', '.join(r['company'] for r in summary['rejections'])}")
        if summary['companies']:
            print(f"\n  Companies active: {', '.join(summary['companies'])}")
        print()

    def get_raw_emails(self, days_back: int = 14, max_results: int = 20) -> list:
        return self.fetch_emails(days_back=days_back, max_results=max_results)


# ─── MCP Server ───────────────────────────────────────────────────────────────

def _run_mcp():
    """Launch the stdio MCP server exposing the Graph tracker as MCP tools.

    Imports `mcp` lazily. Tool calls will surface the Azure/msal setup error if
    the provider is not configured — they never crash the server on import.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("MCP support requires the 'mcp' package: pip install mcp",
              file=sys.stderr)
        sys.exit(1)

    mcp = FastMCP("graph-job-tracker")

    @mcp.tool()
    def sync_graph_to_tracker(days: int = 30, max_results: int = 50) -> dict:
        """Sync + classify recruiter/job email from Microsoft 365 into the pipeline.

        Requires an Azure app registration and the msal/requests packages; if
        unconfigured, raises an error describing the setup steps.
        """
        tracker = GraphTracker()
        return tracker.sync_to_db(days_back=days, max_results=max_results)

    @mcp.tool()
    def get_email_summary(days: int = 30, max_results: int = 50) -> dict:
        """Return a structured summary of recent job email from Microsoft 365.

        Same operation as the CLI --summary. Requires Azure app + msal/requests.
        """
        tracker = GraphTracker()
        return tracker.sync_to_db(days_back=days, max_results=max_results)

    mcp.run()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Microsoft 365 / Outlook (Graph) Job Tracker (ftt) — scaffold')
    parser.add_argument('--sync', action='store_true',
                        help='Sync emails to DB and print summary')
    parser.add_argument('--summary', action='store_true',
                        help='Sync + print summary (alias of --sync)')
    parser.add_argument('--raw', action='store_true',
                        help='Dump raw parsed emails as JSON (no DB write)')
    parser.add_argument('--mcp', action='store_true',
                        help='Run as a stdio MCP server instead of the CLI')
    parser.add_argument('--days', type=int, default=30,
                        help='Days back to search (default: 30)')
    parser.add_argument('--max', type=int, default=50,
                        help='Max emails to fetch (default: 50)')
    args = parser.parse_args()

    if args.mcp:
        _run_mcp()
        return 0

    if not (args.sync or args.summary or args.raw):
        print("Microsoft Graph Job Tracker (scaffold) ready.")
        print("Usage:")
        print("  python3 graph_tracker.py --sync           # sync to DB + print summary")
        print("  python3 graph_tracker.py --raw --days 14  # dump raw emails as JSON")
        print("  python3 graph_tracker.py --summary        # sync + summary")
        print("  python3 graph_tracker.py --mcp            # run as an MCP stdio server")
        print(f"\nNeeds an Azure app + msal/requests — see {DOC_HINT}.")
        return 0

    try:
        tracker = GraphTracker()
        if args.raw:
            emails = tracker.get_raw_emails(days_back=args.days, max_results=args.max)
            for e in emails:
                e['body'] = (e['body'] or '')[:300]
            print(json.dumps(emails, indent=2, default=str))
        else:
            tracker.print_summary(days_back=args.days, max_results=args.max)
        return 0
    except GraphConfigError as e:
        print(f"\n[graph] {e}", file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
