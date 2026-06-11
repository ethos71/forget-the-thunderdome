#!/usr/bin/env python3
"""
Daily Job Search Report - Run each morning
Collects new jobs, shows metrics, tracks follow-ups
"""

import os
import sys
from datetime import datetime
from job_automation import JobSearchDB, ApplicationTracker, InterviewScheduler

def run_daily_report():
    """Generate daily job search report"""
    db = JobSearchDB()
    tracker = ApplicationTracker(db)
    scheduler = InterviewScheduler(db)
    
    print("\n" + "=" * 70)
    print(f"📊 DAILY JOB SEARCH REPORT - {datetime.now().strftime('%A, %B %d, %Y')}")
    print("=" * 70)
    
    # Metrics
    metrics = tracker.get_dashboard()
    print(f"\n📈 METRICS:")
    print(f"   Total Applications: {metrics['total_applications']}")
    print(f"   Responses: {metrics['responses']} ({metrics['response_rate']})")
    print(f"   Interviews: {metrics['interviews_scheduled']}")
    
    # Status breakdown
    print(f"\n📋 STATUS BREAKDOWN:")
    for status, count in sorted(metrics['status_breakdown'].items()):
        print(f"   • {status}: {count}")
    
    # Upcoming interviews
    interviews = scheduler.get_upcoming_interviews()
    if interviews:
        print(f"\n📅 UPCOMING INTERVIEWS (Next 7 Days):")
        for iv in interviews:
            print(f"   • {iv['date']} {iv['time']} - {iv['company']} ({iv['type']})")
    
    # Follow-ups due
    follow_ups = tracker.get_follow_ups_due()
    if follow_ups:
        print(f"\n⚠️ FOLLOW-UPS DUE ({len(follow_ups)}):")
        for fu in follow_ups[:5]:
            print(f"   • {fu['company']} - {fu['role']}")
            print(f"     ID: {fu['application_id']}")
    
    print("\n" + "=" * 70)
    print(f"Next Action: Review follow-ups and check for new opportunities")
    print("=" * 70 + "\n")

if __name__ == '__main__':
    run_daily_report()
