#!/usr/bin/env python3
"""
Self-contained HTML dashboard renderer for forget-the-thunderdome (ftt).

Builds a single static index.html (inline CSS, no external assets, no CDN,
no extra pip deps) from the same data the CLI dashboard uses:
ApplicationTracker.get_dashboard() plus the applications/interviews tables.
"""

import html
import os
from datetime import datetime


def _fetch_recent_applications(db, limit: int = 25):
    """Recent applications: (company, role, status, date_applied)."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT company, role, status, date_applied
        FROM applications
        ORDER BY date_applied DESC
        LIMIT ?
        ''',
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def _fetch_upcoming_interviews(db):
    """All future interviews joined to their application."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT a.company, a.role, i.date, i.time, i.interview_type, i.interviewer
        FROM interviews i
        JOIN applications a ON i.application_id = a.id
        WHERE i.date >= datetime('now')
        ORDER BY i.date, i.time ASC
        '''
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def _e(value) -> str:
    """Escape DB-derived text for safe HTML embedding."""
    return html.escape(str(value if value is not None else ''))


def render_dashboard_html(tracker, out_path: str = "dashboard/index.html") -> str:
    """Render a self-contained HTML dashboard; returns the path written."""
    metrics = tracker.get_dashboard()
    db = tracker.db

    status = metrics['status_breakdown']
    total = metrics['total_applications']
    offers = status.get('offer', 0)
    rejections = status.get('rejected', 0)
    interviews = metrics['interviews_scheduled']
    responses = sum(c for s, c in status.items() if s != 'applied')
    response_rate = f"{(responses / total * 100):.0f}%" if total else "—"

    cards = [
        ("Applications", total),
        ("Interviews", interviews),
        ("Offers", offers),
        ("Rejections", rejections),
        ("Response rate", response_rate),
    ]
    card_html = "\n".join(
        f'    <div class="card"><div class="num">{_e(v)}</div>'
        f'<div class="lbl">{_e(l)}</div></div>'
        for l, v in cards
    )

    app_rows = _fetch_recent_applications(db)
    if app_rows:
        app_body = "\n".join(
            f"      <tr><td>{_e(c)}</td><td>{_e(r)}</td>"
            f'<td><span class="status status-{_e(s)}">{_e(s)}</span></td>'
            f"<td>{_e(d)}</td></tr>"
            for c, r, s, d in app_rows
        )
    else:
        app_body = '      <tr><td colspan="4" class="empty">No applications yet</td></tr>'

    iv_rows = _fetch_upcoming_interviews(db)
    if iv_rows:
        iv_body = "\n".join(
            f"      <tr><td>{_e(c)}</td><td>{_e(r)}</td><td>{_e(d)}</td>"
            f"<td>{_e(t)}</td><td>{_e(it)}</td><td>{_e(iw)}</td></tr>"
            for c, r, d, t, it, iw in iv_rows
        )
    else:
        iv_body = '      <tr><td colspan="6" class="empty">No upcoming interviews</td></tr>'

    generated = _e(metrics.get('date_generated', datetime.now().isoformat()))

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Search Dashboard</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         background: #0f1117; color: #e6e8ee; line-height: 1.5; }}
  .wrap {{ max-width: 960px; margin: 0 auto; padding: 32px 20px 64px; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 4px; }}
  .sub {{ color: #8b90a0; font-size: .85rem; margin-bottom: 28px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
           gap: 14px; margin-bottom: 34px; }}
  .card {{ background: #1a1d27; border: 1px solid #262a37; border-radius: 12px;
          padding: 18px 16px; text-align: center; }}
  .card .num {{ font-size: 1.9rem; font-weight: 700; color: #6ea8fe; }}
  .card .lbl {{ font-size: .78rem; text-transform: uppercase; letter-spacing: .04em;
               color: #8b90a0; margin-top: 4px; }}
  h2 {{ font-size: 1.1rem; margin: 0 0 12px; }}
  section {{ margin-bottom: 34px; }}
  .tw {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
  th, td {{ text-align: left; padding: 9px 12px; border-bottom: 1px solid #262a37;
           white-space: nowrap; }}
  th {{ color: #8b90a0; font-weight: 600; font-size: .78rem; text-transform: uppercase;
       letter-spacing: .04em; }}
  .empty {{ color: #8b90a0; text-align: center; font-style: italic; }}
  .status {{ padding: 2px 9px; border-radius: 999px; font-size: .78rem;
            background: #262a37; color: #cfd3df; }}
  .status-offer {{ background: #123524; color: #6ee7a8; }}
  .status-rejected {{ background: #3a1420; color: #f4a3b4; }}
  .status-interview {{ background: #1a2a44; color: #8fbaff; }}
  @media (prefers-color-scheme: light) {{
    body {{ background: #f6f7f9; color: #1a1d27; }}
    .card, table {{ background: #fff; }}
    .card {{ border-color: #e2e5ec; }}
    th, td {{ border-color: #e2e5ec; }}
    .sub, .card .lbl, th {{ color: #6b7080; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Job Search Dashboard</h1>
  <div class="sub">Generated {generated}</div>
  <div class="cards">
{card_html}
  </div>
  <section>
    <h2>Recent Applications</h2>
    <div class="tw"><table>
      <thead><tr><th>Company</th><th>Role</th><th>Status</th><th>Applied</th></tr></thead>
      <tbody>
{app_body}
      </tbody>
    </table></div>
  </section>
  <section>
    <h2>Upcoming Interviews</h2>
    <div class="tw"><table>
      <thead><tr><th>Company</th><th>Role</th><th>Date</th><th>Time</th><th>Type</th><th>Interviewer</th></tr></thead>
      <tbody>
{iv_body}
      </tbody>
    </table></div>
  </section>
</div>
</body>
</html>
"""

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(doc)
    return out_path
