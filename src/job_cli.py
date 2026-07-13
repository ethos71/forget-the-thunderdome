#!/usr/bin/env python3
"""
Job Search CLI - Command-line interface for automation system
Usage:
  python3 job_cli.py dashboard               # View metrics
  python3 job_cli.py dashboard --html [path] # Render HTML dashboard (default dashboard/index.html)
  python3 job_cli.py apply <company> <role>  # Log application + cover letter
  python3 job_cli.py letter <company> <role> # Generate cover letter
  python3 job_cli.py interview <app_id>      # Schedule interview
  python3 job_cli.py follow-ups              # Show due follow-ups
  python3 job_cli.py calendar [--ics path]   # Export interviews to ICS (default data/interviews.ics)
  python3 job_cli.py crew                    # Run crewAI job search
  python3 job_cli.py jobs [--min-score N]    # Review scraped job postings
  python3 job_cli.py promote <job_id>        # Promote job posting → application
"""

import sys
import os
import json
from datetime import datetime
from job_automation import JobSearchDB, ApplicationTracker, CoverLetterGenerator, InterviewScheduler, print_dashboard

def cmd_dashboard():
    """Show job search dashboard"""
    db = JobSearchDB()
    tracker = ApplicationTracker(db)
    print_dashboard(tracker)

def cmd_dashboard_html(out_path: str = "dashboard/index.html"):
    """Render the dashboard as a self-contained HTML file"""
    from dashboard_html import render_dashboard_html
    db = JobSearchDB()
    tracker = ApplicationTracker(db)
    path = render_dashboard_html(tracker, out_path=out_path)
    print(f"✅ HTML dashboard written: {path}")

def cmd_calendar(out_path: str = "data/interviews.ics"):
    """Export all scheduled interviews to an ICS calendar file"""
    from calendar_export import export_interviews_ics
    db = JobSearchDB()
    path = export_interviews_ics(db, out_path=out_path)
    print(f"✅ Calendar exported: {path}")

def cmd_apply(company: str, role: str, notes: str = None):
    """Log new application"""
    db = JobSearchDB()
    tracker = ApplicationTracker(db)
    
    # Log application
    app_id = tracker.log_application(company, role)
    print(f"✅ Application logged: ID {app_id}")
    print(f"   Company: {company}")
    print(f"   Role: {role}")
    
    # Generate cover letter
    gen = CoverLetterGenerator(db)
    letter = gen.generate(company, role, notes)
    gen.save_letter(app_id, company, role, letter)
    
    print(f"✅ Cover letter generated and saved")
    print("\n" + "-" * 60)
    print(letter)
    print("-" * 60)

def cmd_letter(company: str, role: str):
    """Generate cover letter"""
    db = JobSearchDB()
    gen = CoverLetterGenerator(db)
    
    letter = gen.generate(company, role)
    print(letter)

def cmd_interview(app_id: str, date: str, time: str, interviewer: str = None, email: str = None):
    """Schedule interview"""
    db = JobSearchDB()
    scheduler = InterviewScheduler(db)
    
    interview_id = scheduler.schedule_interview(
        app_id, 'phone_screen', date, time, interviewer, email
    )
    print(f"✅ Interview scheduled: {interview_id}")
    print(f"   Date: {date}")
    print(f"   Time: {time}")
    if interviewer:
        print(f"   Interviewer: {interviewer}")
    if email:
        print(f"   Email: {email}")

def cmd_upcoming():
    """Show upcoming interviews"""
    db = JobSearchDB()
    scheduler = InterviewScheduler(db)
    
    interviews = scheduler.get_upcoming_interviews()
    
    if not interviews:
        print("✅ No interviews scheduled in next 7 days")
        return
    
    print("\n" + "=" * 60)
    print("📅 UPCOMING INTERVIEWS (Next 7 Days)")
    print("=" * 60)
    
    for iv in interviews:
        print(f"\n{iv['company']} - {iv['role']}")
        print(f"  Date: {iv['date']} at {iv['time']}")
        print(f"  Type: {iv['type']}")
        if iv['interviewer']:
            print(f"  Interviewer: {iv['interviewer']}")
        if iv['email']:
            print(f"  Email: {iv['email']}")
        if iv['phone']:
            print(f"  Phone: {iv['phone']}")
        if iv['link']:
            print(f"  Link: {iv['link']}")

def cmd_follow_ups():
    """Show applications due for follow-up"""
    db = JobSearchDB()
    tracker = ApplicationTracker(db)
    
    follow_ups = tracker.get_follow_ups_due()
    
    if not follow_ups:
        print("✅ No follow-ups due")
        return
    
    print("\n" + "=" * 60)
    print("⚠️ FOLLOW-UPS DUE")
    print("=" * 60)
    
    for fu in follow_ups:
        print(f"\n{fu['company']} - {fu['role']}")
        print(f"  Application ID: {fu['application_id']}")
        print(f"  Due: {fu['due_date']}")

def cmd_crew():
    """Run crewAI multi-agent job search"""
    try:
        from job_crew import run_job_crew
        run_job_crew(verbose=True)
    except ImportError as e:
        print(f"❌ Could not load crewAI module: {e}")
        sys.exit(1)


def cmd_jobs(min_score: int = 0):
    """Review scraped job postings from crew"""
    db = JobSearchDB()
    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, company, role, salary_min, salary_max, location, board,
               url, match_score, tags, date_found
        FROM job_postings
        WHERE match_score >= ?
        ORDER BY match_score DESC, date_found DESC
        LIMIT 50
        """,
        (min_score,),
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print(f"No job postings found (min score: {min_score}). Run 'crew' to search.")
        return

    print(f"\n{'='*70}")
    print(f"🔍 JOB POSTINGS ({len(rows)} results, min score: {min_score})")
    print(f"{'='*70}\n")

    for row in rows:
        job_id, company, role, sal_min, sal_max, location, board, url, score, tags_json, found = row
        tags = json.loads(tags_json) if tags_json else []
        sal_str = ""
        if sal_min:
            sal_str = f"${sal_min//1000}k"
            if sal_max:
                sal_str += f"–${sal_max//1000}k"
        tag_str = ", ".join(tags[:4]) if tags else ""
        print(f"[{score or '?':>3}] {company} — {role}")
        print(f"      {sal_str}  |  {location}  |  {board}")
        if tag_str:
            print(f"      Tags: {tag_str}")
        print(f"      URL: {url}")
        print(f"      ID:  {job_id}")
        print()

    print("To apply: python3 job_cli.py promote <job_id>")


def cmd_promote(job_id: str):
    """Promote a scraped job posting to an application"""
    db = JobSearchDB()
    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT company, role, url, salary_min, salary_max FROM job_postings WHERE id = ?",
        (job_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"❌ Job ID not found: {job_id}")
        sys.exit(1)

    company, role, url, sal_min, sal_max = row
    sal_str = f"${sal_min//1000}k–${sal_max//1000}k" if sal_min else ""
    print(f"\n📋 Promoting: {company} — {role} {sal_str}")
    print(f"   URL: {url}")

    tracker = ApplicationTracker(db)
    app_id = tracker.log_application(company, role)
    print(f"✅ Application logged: ID {app_id}")

    gen = CoverLetterGenerator(db)
    print("✍️  Generating cover letter (AI-powered if available)...")
    letter = gen.generate(company, role)
    gen.save_letter(app_id, company, role, letter)

    print("✅ Cover letter generated and saved\n")
    print("-" * 60)
    print(letter)
    print("-" * 60)


def print_help():
    """Print help message"""
    print("""
Job Search Automation CLI

Commands:
  dashboard                  Show job search metrics and summary
  dashboard --html [path]    Render self-contained HTML dashboard (default dashboard/index.html)
  apply <company> <role>     Log new application (generates cover letter)
  letter <company> <role>    Generate cover letter (AI-powered)
  interview <app_id>         Schedule interview (interactive)
  upcoming                   Show upcoming interviews (7 days)
  follow-ups                 Show applications due for follow-up
  calendar [--ics path]      Export all interviews to ICS (default data/interviews.ics)
  crew                       Run crewAI multi-agent job search
  jobs [--min-score N]       Review scraped job postings (default: all)
  promote <job_id>           Promote job posting to application
  help                       Show this message

Examples:
  python3 job_cli.py dashboard
  python3 job_cli.py dashboard --html
  python3 job_cli.py calendar --ics data/interviews.ics
  python3 job_cli.py crew
  python3 job_cli.py jobs --min-score 70
  python3 job_cli.py promote abc123def456
  python3 job_cli.py apply "Example Corp" "Senior Engineer"
  python3 job_cli.py letter "Acme Inc" "Staff Engineer"
  python3 job_cli.py upcoming
  python3 job_cli.py follow-ups
""")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    cmd = sys.argv[1]

    try:
        if cmd == 'dashboard':
            if '--html' in sys.argv:
                idx = sys.argv.index('--html')
                out = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else 'dashboard/index.html'
                cmd_dashboard_html(out)
            else:
                cmd_dashboard()
        elif cmd in ('calendar', 'ics'):
            out = 'data/interviews.ics'
            if '--ics' in sys.argv:
                idx = sys.argv.index('--ics')
                if idx + 1 < len(sys.argv):
                    out = sys.argv[idx + 1]
            cmd_calendar(out)
        elif cmd == 'apply':
            if len(sys.argv) < 4:
                print("Usage: job_cli.py apply <company> <role> [notes]")
                sys.exit(1)
            cmd_apply(sys.argv[2], sys.argv[3], ' '.join(sys.argv[4:]) if len(sys.argv) > 4 else None)
        elif cmd == 'letter':
            if len(sys.argv) < 4:
                print("Usage: job_cli.py letter <company> <role>")
                sys.exit(1)
            cmd_letter(sys.argv[2], sys.argv[3])
        elif cmd == 'interview':
            if len(sys.argv) < 2:
                print("Usage: job_cli.py interview <app_id> <date> <time> [interviewer] [email]")
                sys.exit(1)
            cmd_interview(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None,
                         sys.argv[4] if len(sys.argv) > 4 else None,
                         sys.argv[5] if len(sys.argv) > 5 else None,
                         sys.argv[6] if len(sys.argv) > 6 else None)
        elif cmd == 'upcoming':
            cmd_upcoming()
        elif cmd == 'follow-ups':
            cmd_follow_ups()
        elif cmd == 'crew':
            cmd_crew()
        elif cmd == 'jobs':
            min_score = 0
            if '--min-score' in sys.argv:
                idx = sys.argv.index('--min-score')
                if idx + 1 < len(sys.argv):
                    min_score = int(sys.argv[idx + 1])
            cmd_jobs(min_score)
        elif cmd == 'promote':
            if len(sys.argv) < 3:
                print("Usage: job_cli.py promote <job_id>")
                sys.exit(1)
            cmd_promote(sys.argv[2])
        elif cmd == 'help':
            print_help()
        else:
            print(f"Unknown command: {cmd}")
            print_help()
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
