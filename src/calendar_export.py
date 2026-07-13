#!/usr/bin/env python3
"""
Local ICS (RFC-5545) calendar export for forget-the-thunderdome (ftt).

Writes a VCALENDAR file with one VEVENT per scheduled interview, hand-written
(no icalendar dependency). Local file export only — networked Google/Microsoft
OAuth calendar sync adapters are deferred future work.
"""

import os
from datetime import datetime, timedelta

PRODID = "-//forget-the-thunderdome//ftt calendar export//EN"


def _fetch_all_interviews(db):
    """All interviews joined to their application (not just next 7 days)."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT i.id, a.company, a.role, i.date, i.time, i.interview_type,
               i.interviewer, i.email, i.phone, i.link
        FROM interviews i
        JOIN applications a ON i.application_id = a.id
        ORDER BY i.date, i.time ASC
        '''
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def _esc(text) -> str:
    """Escape ICS TEXT special chars: backslash, comma, semicolon, newline."""
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    s = s.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return s


def _fold(line: str) -> str:
    """Fold a content line to <=75 octets per RFC 5545 (continuation = space)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out = []
    chunk = b""
    for ch in raw:
        b = bytes([ch])
        # keep continuation lines under 75 octets (1 leading space + <=74)
        limit = 75 if not out else 74
        if len(chunk) + 1 > limit:
            out.append(chunk)
            chunk = b
        else:
            chunk += b
    out.append(chunk)
    return "\r\n ".join(c.decode("utf-8", "ignore") for c in out)


def _parse_dt(date_str: str, time_str):
    """Return (datetime|None, all_day_date|None). date_str may include a time."""
    if not date_str:
        return None, None
    d = str(date_str).strip()
    # Try full datetime forms first (DB TIMESTAMP may embed the time).
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(d, fmt), None
        except ValueError:
            continue
    # Fall back to a plain date, optionally combined with an explicit time.
    try:
        day = datetime.strptime(d[:10], "%Y-%m-%d")
    except ValueError:
        return None, None
    t = (str(time_str).strip() if time_str else "")
    if t:
        for fmt in ("%H:%M", "%I:%M %p", "%I%p", "%H:%M:%S"):
            try:
                parsed = datetime.strptime(t, fmt)
                return day.replace(hour=parsed.hour, minute=parsed.minute), None
            except ValueError:
                continue
    return None, day.date()


def _utc_stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _local_stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def export_interviews_ics(db_or_tracker, out_path: str = "data/interviews.ics") -> str:
    """Write a VCALENDAR of all scheduled interviews; returns the path written."""
    db = getattr(db_or_tracker, "db", db_or_tracker)
    rows = _fetch_all_interviews(db)
    now_stamp = _utc_stamp(datetime.utcnow())

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for (iid, company, role, date, time, itype, interviewer, email, phone, link) in rows:
        start_dt, all_day = _parse_dt(date, time)
        if start_dt is None and all_day is None:
            continue  # unparseable date; skip rather than emit invalid event

        summary = f"Interview: {company or ''} — {role or ''}"
        desc_parts = []
        if itype:
            desc_parts.append(f"Type: {itype}")
        if interviewer:
            desc_parts.append(f"Interviewer: {interviewer}")
        if email:
            desc_parts.append(f"Email: {email}")
        if phone:
            desc_parts.append(f"Phone: {phone}")
        description = "\\n".join(_esc(p) for p in desc_parts)

        ev = ["BEGIN:VEVENT", f"UID:{_esc(iid)}@ftt", f"DTSTAMP:{now_stamp}"]
        if start_dt is not None:
            end_dt = start_dt + timedelta(hours=1)
            ev.append(f"DTSTART:{_local_stamp(start_dt)}")
            ev.append(f"DTEND:{_local_stamp(end_dt)}")
        else:
            ev.append(f"DTSTART;VALUE=DATE:{all_day.strftime('%Y%m%d')}")
            ev.append(f"DTEND;VALUE=DATE:{(all_day + timedelta(days=1)).strftime('%Y%m%d')}")
        ev.append(f"SUMMARY:{_esc(summary)}")
        if description:
            ev.append(f"DESCRIPTION:{description}")
        if link:
            ev.append(f"LOCATION:{_esc(link)}")
            ev.append(f"URL:{_esc(link)}")
        ev.append("END:VEVENT")
        lines.extend(ev)

    lines.append("END:VCALENDAR")

    body = "\r\n".join(_fold(l) for l in lines) + "\r\n"

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    return out_path
