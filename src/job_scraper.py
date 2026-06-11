#!/usr/bin/env python3
"""
Job Board Scraper - Find roles matching your profile's search criteria
(target roles, keywords, minimum salary — see profile.yaml).

Scrapes Indeed, LinkedIn, Levels.fyi, AngelList
Stores results in job automation system
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import json
import os
import hashlib
from datetime import datetime
from typing import List, Dict
from job_automation import JobSearchDB
from profile_loader import load_profile

class JobBoardScraper:
    def __init__(self):
        self.db = JobSearchDB()
        search = load_profile().get('search', {})
        self.min_salary = search.get('min_salary', 0)
        self.remote_only = search.get('remote_only', True)
        self.roles = search.get('target_roles', [])
        self.keywords = search.get('keywords', [])
    
    def search_levels_fyi(self) -> List[Dict]:
        """Levels.fyi shows real salaries for tech roles"""
        jobs = []
        # Levels.fyi doesn't have great API, but we can construct URLs
        search_url = "https://www.levels.fyi/jobs?country=US&remote=true"
        
        try:
            response = requests.get(search_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            # Parse would go here - for now return structure
            return jobs
        except Exception as e:
            print(f"❌ Levels.fyi error: {e}")
            return []
    
    def search_linkedin_jobs(self) -> List[Dict]:
        """LinkedIn job search - remote, $150k+"""
        jobs = []
        # LinkedIn has API but requires auth
        # Using web search instead
        print(f"🔍 Searching LinkedIn for: {', '.join(self.roles)} + Remote + ${self.min_salary:,}+")

        salary_k = f"${self.min_salary // 1000}k" if self.min_salary else ""
        search_terms = [f"{role} remote {salary_k}".strip() for role in self.roles]
        
        for term in search_terms:
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={term}&location=Remote"
            try:
                # Would need Selenium or LinkedIn API for actual scrape
                # For now, return template
                pass
            except Exception as e:
                print(f"❌ LinkedIn error: {e}")
        
        return jobs
    
    def search_indeed(self) -> List[Dict]:
        """Indeed job search"""
        jobs = []
        base_url = "https://www.indeed.com/jobs"
        
        params = {
            'q': ' OR '.join(self.roles) if self.roles else 'Software Engineer',
            'l': 'Remote',
            'salary': f'${self.min_salary:,}' if self.min_salary else '',
            'jt': 'fulltime'
        }
        
        try:
            response = requests.get(base_url, params=params, headers={
                'User-Agent': 'Mozilla/5.0'
            })
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Parse job listings
            job_cards = soup.find_all('div', class_='job_seen_beacon')
            
            for card in job_cards[:10]:  # Limit to first 10
                try:
                    title = card.find('h2', class_='jobTitle')
                    company = card.find('span', class_='companyName')
                    salary = card.find('span', class_='salary-snippet')
                    
                    if title and company:
                        jobs.append({
                            'company': company.text.strip(),
                            'role': title.text.strip(),
                            'salary': salary.text.strip() if salary else 'Not listed',
                            'url': card.find('a')['href'],
                            'board': 'Indeed',
                            'date_found': datetime.now().isoformat()
                        })
                except:
                    pass
        
        except Exception as e:
            print(f"❌ Indeed error: {e}")
        
        return jobs
    
    def search_angel_list(self) -> List[Dict]:
        """AngelList - VC-backed startups"""
        jobs = []
        print("🔍 Searching AngelList for startups...")
        
        # AngelList has some public APIs
        try:
            # Would use their API here
            pass
        except Exception as e:
            print(f"❌ AngelList error: {e}")
        
        return jobs
    
    def filter_jobs(self, jobs: List[Dict]) -> List[Dict]:
        """Filter for actual matches"""
        filtered = []
        
        for job in jobs:
            # Must be remote
            if not self._is_remote(job):
                continue
            
            # Must be $150k+
            salary = self._parse_salary(job.get('salary', ''))
            if salary and salary < self.min_salary:
                continue
            
            # Must match role keywords
            role = job.get('role', '').lower()
            if not any(r.lower() in role for r in self.roles):
                continue
            
            filtered.append(job)
        
        return filtered
    
    def _is_remote(self, job: Dict) -> bool:
        """Check if role is remote"""
        location = job.get('location', '').lower()
        role = job.get('role', '').lower()
        
        return 'remote' in location or 'remote' in role
    
    def _parse_salary(self, salary_str: str) -> int:
        """Extract salary number from string like '$150,000 - $200,000'"""
        import re
        match = re.search(r'\$[\d,]+', salary_str)
        if match:
            return int(match.group(0).replace('$', '').replace(',', ''))
        return 0
    
    def save_jobs(self, jobs: List[Dict]):
        """Save found jobs to database"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        saved = 0
        for job in jobs:
            try:
                # Hash URL for unique ID
                job_id = hashlib.md5(job.get('url', job['company']).encode()).hexdigest()[:8]
                
                cursor.execute('''
                    INSERT OR IGNORE INTO job_postings 
                    (id, company, role, salary_min, salary_max, location, board, url, date_found, match_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    job_id,
                    job['company'],
                    job['role'],
                    job.get('salary_min'),
                    job.get('salary_max'),
                    job.get('location', 'Remote'),
                    job['board'],
                    job.get('url', ''),
                    datetime.now(),
                    job.get('match_score', 0)
                ))
                saved += 1
            except Exception as e:
                print(f"⚠️ Could not save {job['company']}: {e}")
        
        conn.commit()
        conn.close()
        print(f"✅ Saved {saved} new jobs to database")
    
    def run(self):
        """Run all scrapers"""
        print("=" * 50)
        print(f"JOB BOARD SCRAPER - ${self.min_salary:,}+ Remote Roles")
        print("=" * 50)
        
        all_jobs = []
        
        # Search multiple boards
        print("\n🔍 Searching job boards...")
        all_jobs.extend(self.search_indeed())
        all_jobs.extend(self.search_levels_fyi())
        all_jobs.extend(self.search_linkedin_jobs())
        all_jobs.extend(self.search_angel_list())
        
        print(f"\n📊 Found {len(all_jobs)} total job listings")
        
        # Filter for matches
        filtered = self.filter_jobs(all_jobs)
        print(f"✅ {len(filtered)} match criteria (${self.min_salary:,}+, Remote, {'/'.join(self.roles)})")
        
        # Save to database
        if filtered:
            self.save_jobs(filtered)
        
        # Show summary
        print("\n" + "=" * 50)
        print(f"SUMMARY: {len(filtered)} new opportunities")
        for job in filtered[:5]:
            print(f"  • {job['company']} - {job['role']}")
        
        return filtered

if __name__ == '__main__':
    import os
    scraper = JobBoardScraper()
    scraper.run()
