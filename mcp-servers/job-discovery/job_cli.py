#!/usr/bin/env python3
"""
Job Discovery CLI
Interact with discovered jobs database
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
import json

# Find project root by looking for data/job_tracker.db
def find_db():
    current = Path(__file__).parent
    for _ in range(5):  # Go up max 5 levels
        candidate = current / 'data' / 'job_tracker.db'
        if candidate.exists():
            return candidate
        current = current.parent
    # Fallback: <repo_root>/data/job_tracker.db (repo root is two levels up)
    fallback = Path(__file__).resolve().parents[2] / 'data' / 'job_tracker.db'
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback

DB_PATH = find_db()

def list_jobs(limit=20, source=None, unapplied_only=True):
    """List discovered jobs"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = 'SELECT id, title, company, salary_min, salary_max, source, match_score, url FROM discovered_jobs WHERE 1=1'
    params = []
    
    if unapplied_only:
        query += ' AND applied = 0'
    
    if source:
        query += ' AND source = ?'
        params.append(source)
    
    query += ' ORDER BY match_score DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    jobs = cursor.fetchall()
    conn.close()
    
    if not jobs:
        print("No jobs found.")
        return
    
    print(f"\n{'ID':<4} {'COMPANY':<15} {'TITLE':<40} {'SALARY':<15} {'SCORE':<6}")
    print("=" * 90)
    
    for job_id, title, company, sal_min, sal_max, source, score, url in jobs:
        sal_range = f"${sal_min//1000}K-${sal_max//1000}K" if sal_min and sal_max else "N/A"
        title_short = (title[:37] + "...") if len(title) > 40 else title
        company_short = (company[:12] + "...") if len(company) > 15 else company
        print(f"{job_id:<4} {company_short:<15} {title_short:<40} {sal_range:<15} {score:<6.2f}")
    
    print(f"\nTotal: {len(jobs)} jobs")

def view_job(job_id):
    """View detailed job info"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM discovered_jobs WHERE id = ?', (job_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print(f"Job {job_id} not found.")
        return
    
    cols = ['id', 'title', 'company', 'location', 'url', 'source', 'salary_min', 
            'salary_max', 'posting_date', 'description', 'discovered_at', 'match_score', 'applied', 'created_at']
    
    print(f"\n{'=' * 60}")
    for col, val in zip(cols, row):
        if col in ['salary_min', 'salary_max'] and val:
            val = f"${val:,}"
        print(f"{col:<20}: {val}")
    print(f"{'=' * 60}\n")

def mark_applied(job_id):
    """Mark job as applied"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('UPDATE discovered_jobs SET applied = 1 WHERE id = ?', (job_id,))
    if cursor.rowcount:
        conn.commit()
        print(f"✓ Job {job_id} marked as applied.")
    else:
        print(f"Job {job_id} not found.")
    
    conn.close()

def summary():
    """Show daily summary"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    today = datetime.now().date()
    
    cursor.execute('SELECT COUNT(*) FROM discovered_jobs WHERE DATE(discovered_at) = ?', (today,))
    total_today = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM discovered_jobs')
    total_all = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM discovered_jobs WHERE applied = 0')
    ready = cursor.fetchone()[0]
    
    cursor.execute('SELECT source, COUNT(*) FROM discovered_jobs GROUP BY source')
    by_source = dict(cursor.fetchall())
    
    conn.close()
    
    print(f"\n📊 JOB DISCOVERY SUMMARY")
    print(f"{'=' * 50}")
    print(f"Discovered today:  {total_today}")
    print(f"All-time total:    {total_all}")
    print(f"Ready to apply:    {ready}")
    print(f"\nBy source:")
    for source, count in sorted(by_source.items()):
        print(f"  • {source.capitalize():<15} {count}")
    print(f"{'=' * 50}\n")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  job-cli list [--source SOURCE] [--limit N]")
        print("  job-cli view <job_id>")
        print("  job-cli apply <job_id>")
        print("  job-cli summary")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'list':
        source = None
        limit = 20
        for arg in sys.argv[2:]:
            if arg.startswith('--source'):
                source = arg.split('=')[1] if '=' in arg else sys.argv[sys.argv.index(arg) + 1]
            elif arg.startswith('--limit'):
                limit = int(arg.split('=')[1] if '=' in arg else sys.argv[sys.argv.index(arg) + 1])
        list_jobs(limit=limit, source=source)
    
    elif cmd == 'view':
        job_id = int(sys.argv[2])
        view_job(job_id)
    
    elif cmd == 'apply':
        job_id = int(sys.argv[2])
        mark_applied(job_id)
    
    elif cmd == 'summary':
        summary()
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == '__main__':
    main()
