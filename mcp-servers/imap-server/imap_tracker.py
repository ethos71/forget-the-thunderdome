#!/usr/bin/env python3
"""
Generic IMAP Job Tracker for forget-the-thunderdome (ftt).

Ingests recruiter / job email from ANY IMAP mailbox (Fastmail, iCloud, a
self-hosted server, Gmail-via-app-password, etc.) using only the Python
standard library (`imaplib` + `email`) — NO third-party packages for the core.

It mirrors the Gmail reference server's shape: classify each message into the
same `email_type` categories, upsert applications + log interactions into the
shared pipeline DB (data/job_tracker.db), and return a summary dict of the same
shape. A `--mcp` flag exposes the same operations as a stdio MCP server.

Config comes from environment variables (an optional profile.yaml email/imap
block is read as a fallback; env always wins):

    FTT_IMAP_HOST       (required)  e.g. imap.fastmail.com
    FTT_IMAP_PORT       (default 993)
    FTT_IMAP_USER       (required)  your login / email address
    FTT_IMAP_PASSWORD   (required)  an APP PASSWORD (not your account password)
    FTT_IMAP_SSL        (default true)  use implicit SSL (IMAP4_SSL)
    FTT_IMAP_FOLDER     (default INBOX)

See docs/providers/imap-setup.md for the full walkthrough.

Standalone:
    python3 imap_tracker.py --sync
    python3 imap_tracker.py --summary --days 14
    python3 imap_tracker.py --mcp        # run as an MCP stdio server
"""

import os
import sys
import json
import re
import email
import email.message
import imaplib
import argparse
import sqlite3
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime, parseaddr
from pathlib import Path
from typing import Optional

# Make src/ (profile_loader, job_automation) importable from this dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from profile_loader import load_profile, default_db_path  # noqa: E402

# Local, unit-testable classifier (mirrors the Gmail keyword rules).
from classify import classify_email  # noqa: E402

# NOTE: the `mcp` package is imported LAZILY inside _run_mcp() (see --mcp) so
# the ordinary CLI keeps working even when `mcp` is not installed.

DOC_HINT = "docs/providers/imap-setup.md"


class ImapConfigError(RuntimeError):
    """Raised when IMAP config is missing/incomplete. Caught for a clean msg."""


# ─── Config ───────────────────────────────────────────────────────────────────

def _truthy(val: str) -> bool:
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on', 'y')


def _profile_imap_block() -> dict:
    """Best-effort read of an imap/email block from profile.yaml.

    Returns a flat dict of the keys we understand (host/port/user/password/
    ssl/folder). Any failure (no profile, no PyYAML, no block) yields {} — the
    profile is a convenience fallback only, never required.
    """
    try:
        profile = load_profile()
    except Exception:
        return {}
    email_block = profile.get('email', {}) or {}
    # Accept either email.imap.* (preferred) or flat email.* keys.
    block = email_block.get('imap', email_block) if isinstance(email_block, dict) else {}
    if not isinstance(block, dict):
        return {}
    out = {}
    for key in ('host', 'port', 'user', 'password', 'ssl', 'folder'):
        if key in block and block[key] not in (None, ''):
            out[key] = block[key]
    return out


def load_imap_config() -> dict:
    """Resolve IMAP config: env vars win, profile.yaml fills gaps.

    Raises ImapConfigError (with a doc pointer) if host/user/password are
    missing after both sources are consulted.
    """
    prof = _profile_imap_block()

    def pick(env_key, prof_key, default=None):
        val = os.environ.get(env_key)
        if val is not None and val != '':
            return val
        if prof_key in prof:
            return prof[prof_key]
        return default

    host = pick('FTT_IMAP_HOST', 'host')
    user = pick('FTT_IMAP_USER', 'user')
    password = pick('FTT_IMAP_PASSWORD', 'password')
    port = pick('FTT_IMAP_PORT', 'port', 993)
    folder = pick('FTT_IMAP_FOLDER', 'folder', 'INBOX')

    ssl_raw = os.environ.get('FTT_IMAP_SSL')
    if ssl_raw is not None and ssl_raw != '':
        use_ssl = _truthy(ssl_raw)
    elif 'ssl' in prof:
        use_ssl = bool(prof['ssl'])
    else:
        use_ssl = True

    missing = [name for name, val in
               (('FTT_IMAP_HOST', host), ('FTT_IMAP_USER', user),
                ('FTT_IMAP_PASSWORD', password)) if not val]
    if missing:
        raise ImapConfigError(
            "IMAP is not configured. Missing: " + ", ".join(missing) + ".\n"
            "Set these environment variables (password should be an APP "
            "PASSWORD):\n"
            "    export FTT_IMAP_HOST=imap.your-provider.com\n"
            "    export FTT_IMAP_USER=you@your-provider.com\n"
            "    export FTT_IMAP_PASSWORD='your-app-password'\n"
            "Optional: FTT_IMAP_PORT (default 993), FTT_IMAP_SSL (default true), "
            "FTT_IMAP_FOLDER (default INBOX).\n"
            f"See {DOC_HINT} for a step-by-step guide."
        )

    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 993

    return {
        'host': host, 'port': port, 'user': user, 'password': password,
        'ssl': use_ssl, 'folder': folder,
    }


# ─── Known companies / extraction (mirrors the Gmail reference helpers) ────────
# NOTE(future refactor): these mirror gmail_tracker.py's extract_* helpers. We
# duplicate rather than import because importing gmail_tracker pulls in Google
# client libraries at module load. A shared src/ module could unify them later.

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
                          'protonmail', 'fastmail'):
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


# ─── IMAP parsing helpers ─────────────────────────────────────────────────────

def _decode(raw) -> str:
    """Decode a possibly RFC2047-encoded header value to a plain str."""
    if raw is None:
        return ''
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


def extract_body(msg: email.message.Message) -> str:
    """Return the best-effort plain-text body of an email.message.Message."""
    try:
        if msg.is_multipart():
            # Prefer text/plain, then fall back to (stripped) text/html.
            for part in msg.walk():
                if part.get_content_type() == 'text/plain' and \
                        'attachment' not in str(part.get('Content-Disposition', '')):
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        return payload.decode(charset, errors='replace')
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        html = payload.decode(charset, errors='replace')
                        return re.sub(r'<[^>]+>', ' ', html)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                text = payload.decode(charset, errors='replace')
                if msg.get_content_type() == 'text/html':
                    text = re.sub(r'<[^>]+>', ' ', text)
                return text
    except Exception:
        pass
    return ''


# ─── DB helper ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(default_db_path())
    conn.row_factory = sqlite3.Row
    return conn


# ─── Core Tracker ─────────────────────────────────────────────────────────────

class ImapJobTracker:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_imap_config()

    def _connect(self):
        cfg = self.config
        if cfg['ssl']:
            imap = imaplib.IMAP4_SSL(cfg['host'], cfg['port'])
        else:
            imap = imaplib.IMAP4(cfg['host'], cfg['port'])
        try:
            imap.login(cfg['user'], cfg['password'])
        except imaplib.IMAP4.error as e:
            raise ImapConfigError(
                f"IMAP login failed for {cfg['user']}@{cfg['host']}: {e}\n"
                "Double-check FTT_IMAP_USER / FTT_IMAP_PASSWORD (use an APP "
                f"PASSWORD, not your account password). See {DOC_HINT}."
            ) from e
        return imap

    def fetch_emails(self, days_back: int = 30, max_results: int = 50) -> list:
        """Fetch + parse recent messages from the configured folder."""
        imap = self._connect()
        emails = []
        try:
            status, _ = imap.select(self.config['folder'], readonly=True)
            if status != 'OK':
                raise ImapConfigError(
                    f"Could not open folder '{self.config['folder']}'. "
                    f"Set FTT_IMAP_FOLDER to a valid mailbox. See {DOC_HINT}."
                )
            since = (datetime.now() - timedelta(days=days_back)).strftime('%d-%b-%Y')
            status, data = imap.search(None, 'SINCE', since)
            if status != 'OK':
                return []
            ids = data[0].split()
            # Newest first, capped at max_results.
            ids = list(reversed(ids))[:max_results]
            for msg_id in ids:
                try:
                    status, msg_data = imap.fetch(msg_id, '(RFC822)')
                    if status != 'OK' or not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)
                    subject = _decode(msg.get('Subject', ''))
                    from_hdr = _decode(msg.get('From', ''))
                    date_hdr = msg.get('Date', '')
                    body = extract_body(msg)
                    message_id = msg.get('Message-ID', '') or \
                        f"imap-{self.config['user']}-{msg_id.decode(errors='replace')}"
                    emails.append({
                        'id': message_id,
                        'subject': subject,
                        'sender': from_hdr,
                        'date': date_hdr,
                        'snippet': body[:200],
                        'body': body,
                        'company': extract_company(subject, body, from_hdr),
                        'role': extract_role(subject, body),
                        'salary': extract_salary(body),
                        'next_steps': extract_next_steps(body),
                        'email_type': classify_email(subject, from_hdr, body),
                    })
                except Exception as e:
                    print(f"Error reading message {msg_id!r}: {e}", file=sys.stderr)
        finally:
            try:
                imap.close()
            except Exception:
                pass
            try:
                imap.logout()
            except Exception:
                pass
        return emails

    def sync_to_db(self, days_back: int = 30, max_results: int = 50) -> dict:
        """Fetch, classify, and upsert into the pipeline DB.

        Returns a summary dict shaped like the Gmail server's.
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
                if new_idx > cur_idx:  # only promote, never demote
                    cursor.execute('UPDATE applications SET status = ? WHERE id = ?',
                                   (new_status, app_id))
            else:
                cursor.execute(
                    'INSERT INTO applications (company, role, date_applied, status, notes) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (company, role, datetime.now().date(), new_status,
                     f"Auto-logged from IMAP email: {em['sender']}"))
                app_id = cursor.lastrowid

            # Log the email interaction (dedupe on message id if possible).
            try:
                cursor.execute(
                    'INSERT OR IGNORE INTO email_interactions '
                    '(application_id, email_from, email_subject, email_date, '
                    'parsed_next_steps, parsed_salary) VALUES (?, ?, ?, ?, ?, ?)',
                    (app_id, em['sender'], em['subject'], em['date'],
                     em['next_steps'], em['salary']))
                summary['logged'] += 1
            except sqlite3.OperationalError:
                # email_interactions table may not exist yet (no email_schema.sql
                # shipped). Try a plain insert; if that also fails, skip logging
                # but keep the upserted application.
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
        print(f"  IMAP Job Tracker — Past {days_back} Days "
              f"({self.config['user']}@{self.config['host']})")
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
    """Launch the stdio MCP server exposing the IMAP tracker as MCP tools.

    Imports `mcp` lazily so the normal CLI runs without the package installed.
    Config is validated on first tool call (not at import), so the server can
    start even before IMAP env vars are set.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("MCP support requires the 'mcp' package: pip install mcp",
              file=sys.stderr)
        sys.exit(1)

    mcp = FastMCP("imap-job-tracker")

    @mcp.tool()
    def sync_imap_to_tracker(days: int = 30, max_results: int = 50) -> dict:
        """Sync + classify recruiter/job email from an IMAP mailbox into the pipeline.

        Fetches the past `days` of email (up to `max_results`), classifies each
        message (interview_invite / offer / rejection / recruiter_outreach /
        application_update), upserts applications and logs interactions into the
        job_tracker DB. Returns a JSON-serializable summary. Raises a clear
        error if FTT_IMAP_* is not configured.
        """
        tracker = ImapJobTracker()
        return tracker.sync_to_db(days_back=days, max_results=max_results)

    @mcp.tool()
    def get_email_summary(days: int = 30, max_results: int = 50) -> dict:
        """Return a structured summary of recent job email from the IMAP mailbox.

        Same operation as the CLI --summary: syncs the past `days` of email to
        the DB and returns totals, counts by type, and the interviews, offers,
        rejections and active companies detected.
        """
        tracker = ImapJobTracker()
        return tracker.sync_to_db(days_back=days, max_results=max_results)

    @mcp.tool()
    def get_recruiter_emails(days: int = 14, max_results: int = 20) -> list:
        """Fetch raw parsed recruiter/job emails from the past `days` (no DB write).

        Read-only inspection of the classified email stream; bodies are
        truncated to keep the payload small.
        """
        tracker = ImapJobTracker()
        emails = tracker.get_raw_emails(days_back=days, max_results=max_results)
        for e in emails:
            e['body'] = (e['body'] or '')[:400]
        return emails

    mcp.run()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Generic IMAP Job Tracker (ftt)')
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
        print("IMAP Job Tracker ready.")
        print("Usage:")
        print("  python3 imap_tracker.py --sync           # sync to DB + print summary")
        print("  python3 imap_tracker.py --raw --days 14  # dump raw emails as JSON")
        print("  python3 imap_tracker.py --summary        # sync + summary")
        print("  python3 imap_tracker.py --mcp            # run as an MCP stdio server")
        print(f"\nConfigure FTT_IMAP_* env vars first — see {DOC_HINT}.")
        return 0

    # Any operation below needs a working config + connection.
    try:
        tracker = ImapJobTracker()
        if args.raw:
            emails = tracker.get_raw_emails(days_back=args.days, max_results=args.max)
            for e in emails:
                e['body'] = (e['body'] or '')[:300]
            print(json.dumps(emails, indent=2, default=str))
        else:
            tracker.print_summary(days_back=args.days, max_results=args.max)
        return 0
    except ImapConfigError as e:
        print(f"\n[imap] {e}", file=sys.stderr)
        return 2
    except (imaplib.IMAP4.error, OSError) as e:
        print(f"\n[imap] Could not reach the IMAP server: {e}\n"
              f"Check FTT_IMAP_HOST / FTT_IMAP_PORT / network. See {DOC_HINT}.",
              file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
