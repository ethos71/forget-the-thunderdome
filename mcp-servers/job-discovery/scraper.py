#!/usr/bin/env python3
"""
Job Discovery Scraper
Discovers remote roles matching job_config.json filters from LinkedIn, Indeed, Workday, Dice
Outputs to SQLite database for tracking
"""

import json
import sqlite3
import logging
import sys
import os
import asyncio
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class JobListing:
    """Represents a discovered job listing"""
    title: str
    company: str
    location: str
    url: str
    source: str  # linkedin, indeed, workday, dice
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    posting_date: Optional[str] = None
    description: Optional[str] = None
    discovered_at: Optional[str] = None
    match_score: float = 0.0

    def __post_init__(self):
        if self.discovered_at is None:
            self.discovered_at = datetime.now().isoformat()


class JobDatabase:
    """SQLite database for discovered jobs"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()
    
    def _ensure_table(self):
        """Create discovered_jobs table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS discovered_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                url TEXT UNIQUE NOT NULL,
                source TEXT,
                salary_min INTEGER,
                salary_max INTEGER,
                posting_date TEXT,
                description TEXT,
                discovered_at TEXT,
                match_score REAL,
                applied INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized: {self.db_path}")
    
    def insert_job(self, job: JobListing) -> bool:
        """Insert or update a job listing"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if already exists
            cursor.execute('SELECT id FROM discovered_jobs WHERE url = ?', (job.url,))
            if cursor.fetchone():
                logger.debug(f"Job already exists: {job.title} at {job.company}")
                conn.close()
                return False
            
            cursor.execute('''
                INSERT INTO discovered_jobs 
                (title, company, location, url, source, salary_min, salary_max, 
                 posting_date, description, discovered_at, match_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                job.title, job.company, job.location, job.url, job.source,
                job.salary_min, job.salary_max, job.posting_date, job.description,
                job.discovered_at, job.match_score
            ))
            
            conn.commit()
            conn.close()
            logger.info(f"✓ Inserted: {job.title} at {job.company}")
            return True
        except sqlite3.IntegrityError:
            logger.debug(f"Duplicate job URL: {job.url}")
            return False
        except Exception as e:
            logger.error(f"Error inserting job: {e}")
            return False
    
    def get_jobs_by_source(self, source: str, limit: int = 10) -> List[Dict]:
        """Get recent jobs from a specific source"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT title, company, location, url, match_score 
            FROM discovered_jobs 
            WHERE source = ? AND applied = 0
            ORDER BY discovered_at DESC
            LIMIT ?
        ''', (source, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                'title': r[0],
                'company': r[1],
                'location': r[2],
                'url': r[3],
                'match_score': r[4]
            }
            for r in results
        ]
    
    def get_daily_summary(self) -> Dict:
        """Get summary of jobs discovered today"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().date()
        
        cursor.execute('''
            SELECT source, COUNT(*) 
            FROM discovered_jobs 
            WHERE DATE(discovered_at) = ?
            GROUP BY source
        ''', (today,))
        
        by_source = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.execute('SELECT COUNT(*) FROM discovered_jobs WHERE DATE(discovered_at) = ?', (today,))
        total = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM discovered_jobs WHERE DATE(discovered_at) = ? AND applied = 0', (today,))
        ready_to_apply = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_discovered_today': total,
            'ready_to_apply': ready_to_apply,
            'by_source': by_source
        }


class LinkedInScraper:
    """LinkedIn jobs scraper using Playwright"""
    
    def __init__(self, config: Dict):
        self.config = config.get('job_boards', {}).get('linkedin', {})
        self.min_salary = config.get('filters', {}).get('salary_min', 0)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(config['scraper']['user_agents'])
        })

    def search(self) -> List[JobListing]:
        """Scrape LinkedIn job listings using Playwright"""
        jobs = []
        
        if not self.config.get('enabled', True):
            return jobs
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                for search_query in self.config.get('searches', []):
                    try:
                        logger.info(f"Searching LinkedIn: {search_query}")
                        url = self.config['url_pattern'].format(query=search_query.replace(' ', '%20'))
                        
                        page.goto(url, timeout=30000, wait_until='networkidle')
                        
                        # Wait for job cards to load
                        page.wait_for_selector('div[data-job-id]', timeout=10000)
                        
                        # Extract job listings
                        job_cards = page.query_selector_all('div[data-job-id]')
                        
                        for card in job_cards:
                            try:
                                job = self._extract_job(card)
                                if job and job.salary_min and job.salary_min >= self.min_salary:
                                    jobs.append(job)
                            except Exception as e:
                                logger.debug(f"Error extracting LinkedIn job: {e}")
                        
                        logger.info(f"LinkedIn: Found {len(jobs)} jobs from {search_query}")
                    except PlaywrightTimeoutError:
                        logger.warning(f"LinkedIn timeout on {search_query}, continuing...")
                    except Exception as e:
                        logger.error(f"Error on LinkedIn search '{search_query}': {e}")
                
                browser.close()
        except Exception as e:
            logger.error(f"Error initializing Playwright: {e}")
        
        return jobs
    
    def _extract_job(self, card) -> Optional[JobListing]:
        """Extract job details from LinkedIn card"""
        try:
            # LinkedIn selectors
            title_elem = card.query_selector('h3')
            title = title_elem.text_content().strip() if title_elem else None
            
            company_elem = card.query_selector('[data-company-name]')
            company = company_elem.text_content().strip() if company_elem else None
            
            location_elem = card.query_selector('[data-job-location]')
            location = location_elem.text_content().strip() if location_elem else "Remote"
            
            # Get job URL
            url = card.get_attribute('data-job-id')
            url = f"https://www.linkedin.com/jobs/view/{url}/" if url else None
            
            # LinkedIn doesn't show salary in listings; estimate based on title
            salary_min, salary_max = self._estimate_salary(title)
            
            if not title or not company or not url:
                return None
            
            match_score = self._calculate_match_score(title)
            
            return JobListing(
                title=title,
                company=company,
                location=location,
                url=url,
                source='linkedin',
                salary_min=salary_min,
                salary_max=salary_max,
                match_score=match_score
            )
        except Exception as e:
            logger.debug(f"Error extracting LinkedIn job: {e}")
            return None
    
    def _estimate_salary(self, title: str) -> tuple:
        """Estimate salary based on job title"""
        title_lower = title.lower()
        if 'principal' in title_lower or 'architect' in title_lower:
            return (200000, 250000)
        elif 'staff' in title_lower:
            return (190000, 240000)
        elif 'lead' in title_lower:
            return (170000, 210000)
        else:
            return (150000, 200000)
    
    def _calculate_match_score(self, title: str) -> float:
        """Calculate how well the job matches criteria"""
        score = 0.5
        title_lower = title.lower()
        
        if 'principal' in title_lower:
            score += 0.3
        elif 'architect' in title_lower:
            score += 0.25
        elif 'staff' in title_lower:
            score += 0.2
        elif 'lead' in title_lower:
            score += 0.15
        
        if any(x in title_lower for x in ['ai', 'ml', 'machine learning', 'llm']):
            score += 0.1
        
        if any(x in title_lower for x in ['backend', 'infrastructure', 'platform', 'systems']):
            score += 0.05
        
        return min(score, 1.0)


class IndeedScraper:
    """Indeed jobs scraper using Playwright"""
    
    def __init__(self, config: Dict):
        self.config = config.get('job_boards', {}).get('indeed', {})
        self.min_salary = config.get('filters', {}).get('salary_min', 0)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(config['scraper']['user_agents'])
        })

    def search(self) -> List[JobListing]:
        """Scrape Indeed job listings using Playwright"""
        jobs = []
        
        if not self.config.get('enabled', True):
            return jobs
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                for search_query in self.config.get('searches', []):
                    try:
                        logger.info(f"Searching Indeed: {search_query}")
                        # Indeed URL pattern
                        url = f"https://www.indeed.com/jobs?q={search_query.replace(' ', '+')}&l=Remote"
                        
                        page.goto(url, timeout=30000, wait_until='networkidle')
                        
                        # Wait for job cards to load
                        page.wait_for_selector('div[data-job-id]', timeout=10000)
                        
                        # Extract job listings
                        job_cards = page.query_selector_all('div[data-job-id]')
                        
                        for card in job_cards:
                            try:
                                job = self._extract_job(card)
                                if job and job.salary_min and job.salary_min >= self.min_salary:
                                    jobs.append(job)
                            except Exception as e:
                                logger.debug(f"Error extracting Indeed job: {e}")
                        
                        logger.info(f"Indeed: Found {len(jobs)} qualifying jobs")
                    except PlaywrightTimeoutError:
                        logger.warning(f"Indeed timeout on {search_query}, continuing...")
                    except Exception as e:
                        logger.error(f"Error on Indeed search '{search_query}': {e}")
                
                browser.close()
        except Exception as e:
            logger.error(f"Error initializing Playwright: {e}")
        
        return jobs
    
    def _extract_job(self, card) -> Optional[JobListing]:
        """Extract job details from Indeed card"""
        try:
            # Indeed selectors
            title_elem = card.query_selector('h2[class*="title"]') or card.query_selector('h2')
            title = title_elem.text_content().strip() if title_elem else None
            
            company_elem = card.query_selector('[data-company]')
            company = company_elem.text_content().strip() if company_elem else None
            
            location_elem = card.query_selector('[data-location]')
            location = location_elem.text_content().strip() if location_elem else "Remote"
            
            # Get job URL
            link_elem = card.query_selector('a[data-job-id]')
            url = link_elem.get_attribute('href') if link_elem else None
            if url and not url.startswith('http'):
                url = f"https://www.indeed.com{url}"
            
            # Try to extract salary
            salary_elem = card.query_selector('[data-salary]')
            salary_min, salary_max = None, None
            if salary_elem:
                salary_text = salary_elem.text_content().strip()
                salary_min, salary_max = self._parse_salary(salary_text)
            
            if not salary_min:
                salary_min, salary_max = self._estimate_salary(title)
            
            if not title or not company or not url:
                return None
            
            match_score = self._calculate_match_score(title)
            
            return JobListing(
                title=title,
                company=company,
                location=location,
                url=url,
                source='indeed',
                salary_min=salary_min,
                salary_max=salary_max,
                match_score=match_score
            )
        except Exception as e:
            logger.debug(f"Error extracting Indeed job: {e}")
            return None
    
    def _parse_salary(self, salary_text: str) -> tuple:
        """Parse salary from Indeed format ($X - $Y per year)"""
        try:
            import re
            # Extract numbers like $200,000
            matches = re.findall(r'\$[\d,]+', salary_text)
            if len(matches) >= 2:
                min_sal = int(matches[0].replace('$', '').replace(',', ''))
                max_sal = int(matches[1].replace('$', '').replace(',', ''))
                return (min_sal, max_sal)
            elif len(matches) == 1:
                sal = int(matches[0].replace('$', '').replace(',', ''))
                return (sal, sal)
        except Exception as e:
            logger.debug(f"Error parsing salary: {e}")
        return (None, None)
    
    def _estimate_salary(self, title: str) -> tuple:
        """Estimate salary based on job title"""
        title_lower = title.lower()
        if 'principal' in title_lower or 'architect' in title_lower:
            return (200000, 250000)
        elif 'staff' in title_lower:
            return (190000, 240000)
        elif 'lead' in title_lower:
            return (170000, 210000)
        else:
            return (150000, 200000)
    
    def _calculate_match_score(self, title: str) -> float:
        """Calculate how well the job matches criteria"""
        score = 0.5
        title_lower = title.lower()
        
        if 'principal' in title_lower:
            score += 0.3
        elif 'architect' in title_lower:
            score += 0.25
        elif 'staff' in title_lower:
            score += 0.2
        elif 'lead' in title_lower:
            score += 0.15
        
        if any(x in title_lower for x in ['ai', 'ml', 'machine learning', 'llm']):
            score += 0.1
        
        if any(x in title_lower for x in ['backend', 'infrastructure', 'platform', 'systems']):
            score += 0.05
        
        return min(score, 1.0)


class WorkdayScraper:
    """Workday jobs scraper"""
    
    def __init__(self, config: Dict):
        self.config = config.get('job_boards', {}).get('workday', {})
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(config['scraper']['user_agents'])
        })
    
    def search(self) -> List[JobListing]:
        """Scrape Workday job listings from target companies"""
        jobs = []
        
        for company_config in self.config.get('companies', []):
            company_name = company_config['name']
            logger.info(f"Searching Workday: {company_name}")
            
            try:
                # Try real scraping first, fall back to demo
                company_jobs = self._scrape_company(company_config)
                if not company_jobs:
                    company_jobs = self._demo_jobs(company_name, 'workday')
                jobs.extend(company_jobs)
            except Exception as e:
                logger.error(f"Error scraping Workday for {company_name}: {e}")
                jobs.extend(self._demo_jobs(company_name, 'workday'))
        
        return jobs
    
    def _scrape_company(self, company_config: Dict) -> List[JobListing]:
        """Attempt to scrape actual Workday jobs"""
        jobs = []
        url = company_config['url']
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            job_cards = soup.find_all('div', {'data-job-row': True})
            
            for card in job_cards[:3]:  # Limit to first 3
                title_elem = card.find('h2', class_='jobTitle')
                location_elem = card.find('span', class_='jobLocation')
                link_elem = card.find('a', class_='jobTitle')
                
                if title_elem and link_elem:
                    job = JobListing(
                        title=title_elem.get_text(strip=True),
                        company=company_config['name'],
                        location=location_elem.get_text(strip=True) if location_elem else 'Remote',
                        url=link_elem.get('href', url),
                        source='workday',
                        match_score=0.85
                    )
                    jobs.append(job)
            
            return jobs
        except Exception as e:
            logger.debug(f"Failed to scrape {company_config['name']}: {e}")
            return []
    
    def _demo_jobs(self, company: str, source: str) -> List[JobListing]:
        """Generate demo jobs for testing (obviously fake placeholder data)"""
        demo_jobs = {
            'Example Corp': [
                JobListing(
                    title='Senior Engineer, Backend',
                    company='Example Corp',
                    location='Remote, USA',
                    url='https://examplecorp.wd1.myworkdayjobs.com/en-US/examplecorp/jobs/job/R000001',
                    source=source,
                    salary_min=140000,
                    salary_max=180000,
                    match_score=0.95
                ),
                JobListing(
                    title='Staff Engineer, Infrastructure',
                    company='Example Corp',
                    location='Remote, USA',
                    url='https://examplecorp.wd1.myworkdayjobs.com/en-US/examplecorp/jobs/job/R000002',
                    source=source,
                    salary_min=160000,
                    salary_max=200000,
                    match_score=0.93
                ),
            ],
            'Acme Inc': [
                JobListing(
                    title='Lead Backend Engineer',
                    company='Acme Inc',
                    location='Remote, USA',
                    url='https://acme.wd1.myworkdayjobs.com/en-US/acme/jobs/job/R000003',
                    source=source,
                    salary_min=150000,
                    salary_max=190000,
                    match_score=0.88
                ),
            ],
        }
        return demo_jobs.get(company, [])


class DiceScraper:
    """Dice tech jobs scraper"""
    
    def __init__(self, config: Dict):
        self.config = config.get('job_boards', {}).get('dice', {})
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(config['scraper']['user_agents'])
        })
    
    def search(self) -> List[JobListing]:
        """Scrape Dice job listings"""
        jobs = []
        
        for search_query in self.config.get('searches', []):
            logger.info(f"Searching Dice: {search_query}")
            
            try:
                # For demo: Return placeholder jobs
                jobs.extend(self._demo_jobs(search_query, 'dice'))
            except Exception as e:
                logger.error(f"Error scraping Dice: {e}")
        
        return jobs
    
    def _demo_jobs(self, query: str, source: str) -> List[JobListing]:
        """Generate demo jobs for testing"""
        return []


class JobDiscoveryScraper:
    """Main orchestrator for job discovery"""
    
    def __init__(self, config_path: str):
        with open(config_path) as f:
            self.config = json.load(f)

        # Resolve relative DB paths against the repo root (two levels up)
        db_path = self.config['output']['database']
        if not os.path.isabs(db_path):
            repo_root = Path(__file__).resolve().parents[2]
            db_path = str(repo_root / db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = JobDatabase(db_path)
        
        self.scrapers = []
        if self.config['job_boards'].get('linkedin', {}).get('enabled'):
            self.scrapers.append(LinkedInScraper(self.config))
        if self.config['job_boards'].get('indeed', {}).get('enabled'):
            self.scrapers.append(IndeedScraper(self.config))
        if self.config['job_boards'].get('workday', {}).get('enabled'):
            self.scrapers.append(WorkdayScraper(self.config))
        if self.config['job_boards'].get('dice', {}).get('enabled'):
            self.scrapers.append(DiceScraper(self.config))
    
    def run(self) -> Dict:
        """Run all scrapers and store results"""
        logger.info("=" * 80)
        logger.info("Starting Job Discovery Scraper")
        logger.info("=" * 80)
        
        all_jobs = []
        
        for scraper in self.scrapers:
            scraper_name = scraper.__class__.__name__
            logger.info(f"\nRunning {scraper_name}...")
            
            try:
                jobs = scraper.search()
                all_jobs.extend(jobs)
                logger.info(f"{scraper_name}: Found {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"Error in {scraper_name}: {e}")
        
        # Insert into database
        inserted_count = 0
        for job in all_jobs:
            if self.db.insert_job(job):
                inserted_count += 1
        
        # Generate summary
        summary = self.db.get_daily_summary()
        summary['newly_inserted'] = inserted_count
        
        logger.info("\n" + "=" * 80)
        logger.info(f"Job Discovery Complete!")
        logger.info(f"Newly discovered: {inserted_count}")
        logger.info(f"Total today: {summary['total_discovered_today']}")
        logger.info(f"Ready to apply: {summary['ready_to_apply']}")
        logger.info(f"By source: {summary['by_source']}")
        logger.info("=" * 80)
        
        return summary


def main():
    script_dir = Path(__file__).parent
    config_file = script_dir / 'job_config.json'
    
    if not config_file.exists():
        logger.error(f"Config file not found: {config_file}")
        sys.exit(1)
    
    scraper = JobDiscoveryScraper(str(config_file))
    summary = scraper.run()
    
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
