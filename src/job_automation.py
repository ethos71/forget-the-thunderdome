#!/usr/bin/env python3
"""
Job Search Automation System - Complete Workflow
Part of forget-the-thunderdome (ftt). All personal data comes from
profile.yaml — see profile.yaml.example.

Includes:
1. Enhanced Job Scraper (Indeed, LinkedIn, Levels.fyi)
2. Application Tracker Dashboard
3. Cover Letter Generator (AutoGen-powered with template fallback)
4. Interview Scheduler
"""

import sqlite3
import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import hashlib

from profile_loader import load_profile, default_db_path

class JobSearchDB:
    """Database management for job search tracking"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = default_db_path()
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Applications table (primary tracking table)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT DEFAULT 'applied',
                notes TEXT,
                date_applied TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company, role)
            )
        ''')

        # Job postings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS job_postings (
                id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                salary_min INTEGER,
                salary_max INTEGER,
                location TEXT,
                board TEXT,
                url TEXT UNIQUE,
                description TEXT,
                date_found TIMESTAMP,
                match_score INTEGER,
                tags TEXT
            )
        ''')
        
        # Interviews table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interviews (
                id TEXT PRIMARY KEY,
                application_id INTEGER,
                interview_type TEXT,
                date TIMESTAMP,
                time TEXT,
                interviewer TEXT,
                email TEXT,
                phone TEXT,
                link TEXT,
                questions_asked TEXT,
                feedback TEXT,
                next_steps TEXT,
                FOREIGN KEY (application_id) REFERENCES applications(id)
            )
        ''')
        
        # Cover letter templates
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cover_letters (
                id TEXT PRIMARY KEY,
                company TEXT,
                role TEXT,
                content TEXT,
                date_created TIMESTAMP,
                application_id INTEGER,
                FOREIGN KEY (application_id) REFERENCES applications(id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)

class ApplicationTracker:
    """Track applications and metrics"""
    
    def __init__(self, db: JobSearchDB):
        self.db = db
    
    def log_application(self, company: str, role: str, cover_letter: str = None) -> int:
        """Log new application - returns application ID"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO applications (company, role, status, notes, date_applied)
                VALUES (?, ?, 'applied', ?, datetime('now'))
            ''', (company, role, cover_letter or ''))
            conn.commit()
            app_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            # Application already exists, get its ID
            cursor.execute('SELECT id FROM applications WHERE company = ? AND role = ?', 
                          (company, role))
            app_id = cursor.fetchone()[0]
        finally:
            conn.close()
        
        return app_id
    
    def update_status(self, app_id: int, status: str):
        """Update application status"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE applications 
            SET status = ?
            WHERE id = ?
        ''', (status, app_id))
        
        conn.commit()
        conn.close()
    
    def set_follow_up(self, app_id: int, days: int = 7):
        """Schedule follow-up reminder"""
        follow_up = datetime.now() + timedelta(days=days)
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Add to notes since we don't have follow_up_date in existing schema
        cursor.execute('''
            UPDATE applications 
            SET notes = COALESCE(notes, '') || 'Follow-up scheduled for: ' || ?
            WHERE id = ?
        ''', (follow_up.strftime('%Y-%m-%d'), app_id))
        
        conn.commit()
        conn.close()
    
    def get_dashboard(self) -> Dict:
        """Get job search metrics"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Total applications
        cursor.execute('SELECT COUNT(*) FROM applications')
        total_apps = cursor.fetchone()[0]
        
        # Status breakdown
        cursor.execute('SELECT status, COUNT(*) FROM applications GROUP BY status')
        status_breakdown = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Companies applied to
        cursor.execute('''
            SELECT company, COUNT(*) 
            FROM applications
            GROUP BY company
            ORDER BY COUNT(*) DESC
        ''')
        companies = cursor.fetchall()
        
        # Interviews
        cursor.execute('SELECT COUNT(*) FROM interviews')
        interviews = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_applications': total_apps,
            'status_breakdown': status_breakdown,
            'top_companies': companies[:5],
            'interviews_scheduled': interviews,
            'date_generated': datetime.now().isoformat()
        }
    
    def get_follow_ups_due(self) -> List[Dict]:
        """Get applications needing follow-up (no follow-up contact in 7+ days)"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Applications with status 'applied' that haven't been updated in 7+ days
        cursor.execute('''
            SELECT id, company, role, date_applied
            FROM applications
            WHERE status = 'applied'
            AND date_applied <= date('now', '-7 days')
            ORDER BY date_applied ASC
        ''')
        
        follow_ups = []
        for row in cursor.fetchall():
            follow_ups.append({
                'application_id': row[0],
                'company': row[1],
                'role': row[2],
                'date_applied': row[3]
            })
        
        conn.close()
        return follow_ups

class CoverLetterGenerator:
    """Generate tailored cover letters"""
    
    def __init__(self, db: JobSearchDB, profile: dict = None):
        self.db = db
        self.profile = profile or load_profile()

    def extract_relevant_accomplishment(self, role: str, company: str) -> str:
        """Find relevant accomplishment for role from profile narrative.

        Picks the first key_strength bullet whose text shares a keyword with
        the role/company; falls back to the first strength or elevator pitch.
        """
        strengths = self.profile.get('narrative', {}).get('key_strengths', [])
        text = f"{role} {company}".lower()
        for strength in strengths:
            if any(word in text for word in strength.lower().split() if len(word) > 4):
                return strength
        if strengths:
            return strengths[0]
        return self.profile.get('narrative', {}).get('elevator_pitch', '').strip()

    def generate(self, company: str, role: str, job_description: str = None) -> str:
        """Generate tailored cover letter — uses AutoGen if available, else template."""
        try:
            from cover_letter_agent import generate_cover_letter
            return generate_cover_letter(company, role, job_description)
        except Exception:
            return self._template_generate(company, role, job_description)

    def _template_generate(self, company: str, role: str, job_description: str = None) -> str:
        """Template-based cover letter (always available fallback)."""
        identity = self.profile.get('identity', {})
        narrative = self.profile.get('narrative', {})

        name = identity.get('name', '')
        pitch = (narrative.get('elevator_pitch') or '').strip()
        strengths = narrative.get('key_strengths', [])
        tech_summary = narrative.get('tech_summary', '')

        strength_bullets = "\n".join(f"• {s}" for s in strengths[:4]) or "• [Add key_strengths to profile.yaml]"
        contact_lines = "\n".join(
            x for x in [name, identity.get('phone', ''), identity.get('email', ''),
                        identity.get('github', '')] if x
        )

        letter = f"""Dear Hiring Manager,

{pitch} I'm excited about {company}'s {role} position.

**Why I'm a fit:**

Your role emphasizes {self._extract_key_requirement(job_description or role)}. My recent work directly demonstrates this:

{strength_bullets}

**Technical depth:** {tech_summary}

**What excites me about {company}:**
You're solving problems that matter at scale, and this role lines up directly with the work I do best.

I'm ready to bring proven execution and ownership to your challenges.

Best regards,
{contact_lines}
"""

        return letter
    
    def _extract_key_requirement(self, text: str) -> str:
        """Extract key requirement from job description"""
        if not text:
            return "building scalable systems"
        
        keywords = {
            'ai': 'deploying AI at scale',
            'ml': 'machine learning systems',
            'data': 'data infrastructure',
            'fraud': 'fraud detection',
            'compliance': 'regulatory compliance',
            'architect': 'system architecture',
            'fintech': 'fintech solutions',
            'lead': 'team leadership'
        }
        
        text_lower = text.lower()
        for key, value in keywords.items():
            if key in text_lower:
                return value
        
        return "solving complex technical challenges"
    
    def save_letter(self, app_id: int, company: str, role: str, content: str):
        """Save generated letter to database"""
        letter_id = f"letter-{hashlib.md5(f'{app_id}-{datetime.now()}'.encode()).hexdigest()[:8]}"
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO cover_letters 
            (id, company, role, content, date_created, application_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (letter_id, company, role, content, datetime.now(), app_id))
        
        conn.commit()
        conn.close()
        
        return letter_id

class InterviewScheduler:
    """Manage interview scheduling and follow-ups"""
    
    def __init__(self, db: JobSearchDB):
        self.db = db
    
    def schedule_interview(self, app_id: int, interview_type: str, 
                          date: str, time: str, interviewer: str = None,
                          email: str = None, phone: str = None, link: str = None) -> str:
        """Schedule interview"""
        interview_id = f"iv-{hashlib.md5(f'{app_id}-{date}'.encode()).hexdigest()[:8]}"
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO interviews
            (id, application_id, interview_type, date, time, interviewer, email, phone, link)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (interview_id, app_id, interview_type, date, time, interviewer, email, phone, link))
        
        conn.commit()
        conn.close()
        
        return interview_id
    
    def get_upcoming_interviews(self) -> List[Dict]:
        """Get interviews in next 7 days"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        future = datetime.now() + timedelta(days=7)
        
        cursor.execute('''
            SELECT i.id, a.company, a.role, i.date, i.time, i.interview_type,
                   i.interviewer, i.email, i.phone, i.link
            FROM interviews i
            JOIN applications a ON i.application_id = a.id
            WHERE i.date BETWEEN datetime('now') AND ?
            ORDER BY i.date, i.time ASC
        ''', (future.isoformat(),))
        
        interviews = []
        for row in cursor.fetchall():
            interviews.append({
                'id': row[0],
                'company': row[1],
                'role': row[2],
                'date': row[3],
                'time': row[4],
                'type': row[5],
                'interviewer': row[6],
                'email': row[7],
                'phone': row[8],
                'link': row[9]
            })
        
        conn.close()
        return interviews
    
    def log_interview_feedback(self, interview_id: str, questions: str, 
                              feedback: str, next_steps: str = None):
        """Log post-interview details"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE interviews
            SET questions_asked = ?, feedback = ?, next_steps = ?
            WHERE id = ?
        ''', (questions, feedback, next_steps, interview_id))
        
        conn.commit()
        conn.close()

def print_dashboard(tracker: ApplicationTracker):
    """Print formatted dashboard"""
    metrics = tracker.get_dashboard()
    
    print("\n" + "=" * 60)
    print("📊 JOB SEARCH DASHBOARD")
    print("=" * 60)
    print(f"\nTotal Applications: {metrics['total_applications']}")
    print(f"Interviews Scheduled: {metrics['interviews_scheduled']}")
    print(f"\nStatus Breakdown:")
    for status, count in sorted(metrics['status_breakdown'].items()):
        print(f"  • {status}: {count}")
    
    if metrics['top_companies']:
        print(f"\nTop Companies Applied To:")
        for company, count in metrics['top_companies']:
            print(f"  • {company}: {count} applications")
    
    print("\n" + "=" * 60)

if __name__ == '__main__':
    db = JobSearchDB()
    tracker = ApplicationTracker(db)
    
    print_dashboard(tracker)
