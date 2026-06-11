---
name: job-discovery
description: |
  Discovers new job postings matching the user's criteria from major job boards.
  Runs daily to find roles matching profile.yaml's search section (target_roles,
  keywords, min_salary, remote_only). Outputs to the discovered_jobs table in
  data/job_tracker.db for curation.
---

# Job Discovery MCP Server

> **Invoke this skill when**: Running daily job discovery scrape, manually refreshing job boards,
> or searching for jobs in a specific niche (e.g., "Show me all Example Corp jobs in the market").

## Core Purpose

Daily automated scraping of major job boards to surface opportunities matching the user's constraints
(see `profile.yaml` and `job_config.json`). Filters out non-matching roles early.
Presents a curated list for manual approval.

## Supported Job Boards

### Tier 1 (Primary - Cover ~80% of tech jobs)
- **LinkedIn**: Remote + target-role searches (via search + email alerts parsing)
- **Indeed**: Queries built from your target roles
- **Workday**: Workday instances of your target companies (configure in `job_config.json`)

### Tier 2 (Secondary - Niche high-quality boards)
- **Dice**: Tech specialist board, strong filters
- **Blind**: Tech community-driven (insider perspectives)
- **YC Jobs**: Startup focus

### Tier 3 (Manual - Direct company career pages)
- Your target companies (see `profile.yaml` search.target_companies)
- (Can be scraped or checked manually)

## Filter Criteria

All criteria come from your `profile.yaml` search section and `job_config.json` filters:

**Hard Constraints** (must match all):
- Role level: matches `search.target_roles`
- Location: Remote (if `search.remote_only`) or matches `search.locations`
- Salary: `search.min_salary`+ (if posted)

**Soft Constraints** (preferential):
- Domain: matches `search.keywords` (in priority order)
- Company stage: no preference by default

**Exclusions**:
- Contract, Consulting, Temp roles
- 1099, C2C arrangements
- Companies with known hiring freezes
- Visa sponsorship required (unless explicitly stated)

## Daily Workflow

```
6:00 AM  → job-discovery server wakes up
6:05 AM  → Scrape LinkedIn, Indeed, Workday
6:20 AM  → Filter for matching criteria
6:25 AM  → Insert into discovered_jobs table
6:30 AM  → Notify the user: "35 new jobs found"
→        → User curates + approves ~15 for application
```

## Output Format

### discovered_jobs Table
```sql
CREATE TABLE discovered_jobs (
  id INT PRIMARY KEY AUTO_INCREMENT,
  job_url VARCHAR(255) UNIQUE,
  company VARCHAR(100),
  role_title VARCHAR(150),
  source VARCHAR(50),  -- 'linkedin', 'indeed', 'workday', etc
  discovered_date TIMESTAMP,
  salary_range VARCHAR(50),
  description TEXT,
  location VARCHAR(100),
  status ENUM('discovered', 'approved', 'skip', 'applied'),
  reason_skipped TEXT,
  user_notes TEXT
);
```

### Example Output (Daily Report)
```
=== JOB DISCOVERY REPORT (2026-04-29) ===

35 New Jobs Found
├─ LinkedIn: 12 jobs
├─ Indeed: 8 jobs
├─ Workday: 10 jobs
├─ Dice: 5 jobs
└─ Other: 0 jobs

TOP MATCHES (for user review):
1. Example Corp — Senior Engineer, Infrastructure
   └─ Remote, $140-180K, Posted 1h ago
   └─ https://examplecorp.com/careers/...

2. Acme Inc — Staff Engineer, Platform
   └─ Remote, $150-190K, Posted 3h ago
   └─ https://acme.example/careers/...

... (25 more)

ACTION: review these and approve for application
```

## Implementation Details

### Technology Stack
- **Python 3.10+**
- **Playwright** or **Selenium** (handle JavaScript-heavy job boards)
- **BeautifulSoup** (HTML parsing)
- **SQLite** (tracking)
- **Redis** (job queue for async processing)

### Scraper Components

#### LinkedIn Scraper
- Method 1 (Preferred): Parse email alerts + RSS feeds
- Method 2: Web scraper with login (higher maintenance)
- Filters: Job title, location, salary (if available)
- Output: URL + basic metadata

#### Indeed Scraper
- Search query: "Principal Engineer" OR "Staff Engineer" OR "Architect", Remote
- Pagination: First 10 pages (covers most relevant results)
- Filters: Posted in last 24h, salary $150K+
- Output: URL + posting date + salary

#### Workday Scraper
- Target instances: your target companies (configure in job_config.json)
- Search: Keyword "Principal" OR "Staff" OR "Architect"
- Location: Remote
- Output: URL + metadata

#### Dice/Blind/Others
- Similar approach: search query → filter → extract URLs

### Error Handling
- Network timeouts: Retry with exponential backoff
- Rate limiting: Respect robots.txt, add delays
- Parsing failures: Log + escalate to the user
- Duplicate URLs: Skip if already in discovered_jobs table

## Configuration

```json
{
  "job_boards": [
    {
      "name": "linkedin",
      "enabled": true,
      "scrape_frequency": "daily",
      "search_terms": ["Principal Engineer remote", "Staff Engineer remote", "Architect remote"],
      "min_salary": 150000
    },
    {
      "name": "indeed",
      "enabled": true,
      "scrape_frequency": "daily",
      "search_query": "(\"Principal Engineer\" OR \"Staff Engineer\" OR \"Architect\") AND remote AND $150000",
      "location": "remote"
    },
    {
      "name": "workday",
      "enabled": true,
      "scrape_frequency": "daily",
      "instances": [
        "databricks.wd5.myworkdayjobs.com",
        "anthropic.wd5.myworkdayjobs.com",
        "stripe.wd1.myworkdayjobs.com"
      ]
    }
  ],
  "filters": {
    "min_salary": 150000,
    "required_location": "remote",
    "exclude_keywords": ["contract", "consulting", "visa sponsorship required"],
    "include_keywords": ["principal", "staff", "architect", "lead"]
  }
}
```

## Daily Schedule (GitHub Actions)

```yaml
name: Daily Job Discovery
on:
  schedule:
    - cron: '0 6 * * *'  # 6am daily
jobs:
  discover:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run job discovery
        run: python mcp-servers/job-discovery/scraper.py
      - name: Upload results
        run: sqlite3 data/job_tracker.db < discovered_jobs.sql
      - name: Notify the user
        run: |
          COUNT=$(sqlite3 data/job_tracker.db "SELECT COUNT(*) FROM discovered_jobs WHERE status='discovered' AND discovered_date >= datetime('now', '-1 day')")
          echo "$COUNT new jobs discovered. Ready for curation."
```

## Integration Points

| Component | Usage |
|-----------|-------|
| `form-parser` MCP | Takes approved jobs from discovered_jobs → extracts form fields |
| `job_tracker.db` | Stores discovered_jobs + curation status |
| application workflow | Orchestrates discovery → parsing → submission |
| GitHub Actions | Triggers daily discovery, notifies the user |

## Success Metrics

- **Volume**: 30–50 new matching jobs discovered daily
- **Quality**: >80% of discovered jobs match the profile's criteria (target roles, remote, min salary)
- **False positives**: <5% of results are non-matching (filtered out properly)
- **Curation rate**: user approves 30–50% for application (realistic ratio)

## References

| File | Purpose |
|------|---------|
| `profile.yaml` (repo root) | Search criteria source of truth |
| `mcp-servers/job-discovery/job_config.json` | Scraper configuration |
| `mcp-servers/form-parser/` | Downstream: parses approved jobs |
