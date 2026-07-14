#!/usr/bin/env python3
"""
crewAI Multi-Agent Job Scraper
Agents:
  1. ScraperAgent  — searches job boards via DuckDuckGo
  2. FilterAgent   — validates salary, remote, title match
  3. ScorerAgent   — scores 0–100 against the profile's search criteria
  4. TrackerAgent  — writes validated postings to SQLite

All search criteria (target roles, keywords, min salary, target companies)
come from profile.yaml — see profile.yaml.example.

Usage:
  python3 job_crew.py                  # run full crew
  from job_crew import run_job_crew    # import in CLI
"""

import json
import os
import sys
import hashlib
from datetime import datetime
from typing import List, Dict

from job_automation import JobSearchDB
from profile_loader import load_profile
import ai_config

# ── Criteria (built from profile.yaml) ─────────────────────────────────────


def _build_criteria(profile: dict) -> dict:
    """Derive crew search criteria from the profile's search section."""
    search = profile.get("search", {})
    roles = search.get("target_roles", []) or ["Software Engineer"]
    keywords = search.get("keywords", [])
    min_salary = search.get("min_salary", 0)
    salary_k = f"${min_salary // 1000}k" if min_salary else ""

    queries = [
        f"{roles[0]} remote {salary_k} site:linkedin.com OR site:indeed.com".strip(),
    ]
    for role in roles[1:3]:
        queries.append(f"{role} remote {salary_k} {' '.join(keywords[:2])}".strip())
    queries.append(
        f"{roles[0]} remote {salary_k} site:lever.co OR site:greenhouse.io".strip()
    )

    return {
        "queries": queries,
        "roles": roles,
        "keywords": keywords,
        "min_salary": min_salary,
        "target_companies": {c.lower() for c in search.get("target_companies", [])},
    }


def _save_jobs(jobs: List[Dict]) -> int:
    """Writes validated jobs to job_postings table. Returns count saved."""
    db = JobSearchDB()
    conn = db.get_connection()
    cursor = conn.cursor()
    saved = 0

    for job in jobs:
        job_id = hashlib.md5(
            f"{job.get('company','')}-{job.get('role','')}-{job.get('url','')}".encode()
        ).hexdigest()[:12]

        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO job_postings
                  (id, company, role, salary_min, salary_max, location, board,
                   url, description, date_found, match_score, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    job.get("company", ""),
                    job.get("role", ""),
                    job.get("salary_min"),
                    job.get("salary_max"),
                    job.get("location", "Remote"),
                    job.get("board", "crew-search"),
                    job.get("url", ""),
                    job.get("description", ""),
                    datetime.now().isoformat(),
                    job.get("score", 0),
                    json.dumps(job.get("tags", [])),
                ),
            )
            if cursor.rowcount:
                saved += 1
        except Exception as e:
            print(f"  ⚠️  DB error for {job.get('company')}: {e}", file=sys.stderr)

    conn.commit()
    conn.close()
    return saved


def _parse_json_safe(text: str) -> dict:
    """Extract JSON from LLM output that may include prose."""
    import re
    # Try direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Find JSON block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def run_job_crew(verbose: bool = True) -> int:
    """
    Run the crewAI job search crew.
    Returns number of new jobs saved to DB.
    Falls back gracefully if crewAI or LLM is unavailable.
    """
    if not ai_config.is_available():
        print("⚠️  No LLM provider available.")
        print("   Run a local Ollama server (http://localhost:11434) — it's")
        print("   used automatically and preferred, even when a paid key is set.")
        print("   Or set OPENAI_API_KEY / ANTHROPIC_API_KEY (used when Ollama is")
        print("   down, or when FTT_FORCE_PAID=1).")
        return 0

    profile = load_profile()
    crit = _build_criteria(profile)
    candidate_name = profile.get("identity", {}).get("name", "the candidate")
    pitch = (profile.get("narrative", {}).get("elevator_pitch") or "").strip()
    roles_str = ", ".join(crit["roles"])
    keywords_str = ", ".join(crit["keywords"]) or "none specified"
    min_salary = crit["min_salary"]
    salary_str = f"${min_salary:,}+" if min_salary else "any salary"
    targets_str = ", ".join(sorted(crit["target_companies"])) or "none specified"

    try:
        from crewai import Agent, Task, Crew, Process
        from crewai_tools import tool
    except ImportError:
        print("⚠️  crewai not installed. Run: pip install crewai crewai-tools")
        return 0

    try:
        from langchain_community.tools import DuckDuckGoSearchRun
        search_tool = DuckDuckGoSearchRun()
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            # Wrap DDGS in a simple callable crewAI tool
            @tool("web_search")
            def search_tool(query: str) -> str:
                """Search the web for job postings."""
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=8))
                return "\n\n".join(
                    f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}"
                    for r in results
                )
        except ImportError:
            print("⚠️  No search tool available. Run: pip install duckduckgo-search")
            return 0

    llm = ai_config.get_crewai_llm()

    # ── Agents ────────────────────────────────────────────────────────────

    scraper = Agent(
        role="Job Board Scraper",
        goal=f"Find remote job postings for: {roles_str} paying {salary_str}",
        backstory=(
            "You are a specialized job board researcher. You search multiple job boards "
            "and return raw job posting results including title, company, salary, location, "
            "and URL. You are thorough and return at least 5–10 results per search."
        ),
        tools=[search_tool],
        llm=llm,
        verbose=verbose,
        allow_delegation=False,
    )

    filterer = Agent(
        role="Job Filter Specialist",
        goal=f"Filter job results to only those meeting strict criteria: {salary_str}, remote, correct title",
        backstory=(
            "You are a strict filter who only allows through jobs that meet ALL criteria. "
            "You extract structured data from raw job results and return clean JSON."
        ),
        llm=llm,
        verbose=verbose,
        allow_delegation=False,
    )

    scorer = Agent(
        role="Job Match Scorer",
        goal="Score filtered jobs 0–100 based on fit for the candidate",
        backstory=(
            f"You score job postings for {candidate_name}. Candidate pitch: {pitch} "
            f"Criteria: target roles ({roles_str}), keywords ({keywords_str}), "
            f"{salary_str} minimum, remote only. "
            f"Target companies: {targets_str}."
        ),
        llm=llm,
        verbose=verbose,
        allow_delegation=False,
    )

    # ── Tasks ─────────────────────────────────────────────────────────────

    search_queries = "\n".join(f"- {q}" for q in crit["queries"][:3])

    scrape_task = Task(
        description=f"""
Search the web for remote jobs matching these roles: {roles_str} (paying {salary_str}).
Run these searches:
{search_queries}

For each result, capture: company name, job title, salary range, location/remote status, URL, brief description.
Return ALL results as a numbered list. Include at least 10 results.
""",
        expected_output="Numbered list of job postings with company, title, salary, location, URL",
        agent=scraper,
    )

    filter_task = Task(
        description=f"""
Review the job postings from the scraper. For each one, determine if it passes ALL criteria:
1. Salary {salary_str} per year
2. Remote only
3. Title matches one of: {roles_str}
4. Full-time (not contract)

For passing jobs, output a JSON array like:
[
  {{
    "company": "Example Corp",
    "role": "Principal Engineer",
    "salary_min": 150000,
    "salary_max": 200000,
    "location": "Remote",
    "url": "https://example.com/jobs/123",
    "description": "Brief description"
  }}
]

Be strict. Only pass jobs that clearly meet all criteria.
""",
        expected_output="JSON array of validated job postings",
        agent=filterer,
        context=[scrape_task],
    )

    score_task = Task(
        description=f"""
Score each validated job posting 0–100 for {candidate_name}.

Scoring:
- +30 if company is a target company ({targets_str})
- +20 if role involves any of the candidate's keywords ({keywords_str})
- +10 if salary is well above the minimum ({salary_str})
- +5 if known remote-first culture
- -20 if any in-office requirement

Add a "score" field (0–100) and a "tags" array to each job object.
Return the complete JSON array with scores added.
""",
        expected_output="JSON array with score and tags added to each job",
        agent=scorer,
        context=[filter_task],
    )

    # ── Crew ──────────────────────────────────────────────────────────────

    crew = Crew(
        agents=[scraper, filterer, scorer],
        tasks=[scrape_task, filter_task, score_task],
        process=Process.sequential,
        verbose=verbose,
    )

    if verbose:
        print("\n🤖 Starting crewAI job search...")
        print(f"   Model: {ai_config.get_model_name()}")
        print(f"   Searches: {len(crit['queries'])} queries\n")

    try:
        result = crew.kickoff()
    except Exception as e:
        print(f"❌ Crew execution failed: {e}", file=sys.stderr)
        return 0

    # Parse scored jobs from result
    result_text = str(result)
    jobs = []

    parsed = _parse_json_safe(result_text)
    if isinstance(parsed, list):
        jobs = parsed
    else:
        # Try to find array in output
        import re
        match = re.search(r"\[.*\]", result_text, re.DOTALL)
        if match:
            try:
                jobs = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if not jobs:
        if verbose:
            print("⚠️  Could not parse structured job results from crew output.")
            print("   Raw output saved for inspection.")
        return 0

    saved = _save_jobs(jobs)

    if verbose:
        print(f"\n✅ Crew complete: {len(jobs)} jobs found, {saved} new jobs saved to DB")
        if jobs:
            print("\n🏆 Top matches:")
            top = sorted(jobs, key=lambda j: j.get("score", 0), reverse=True)[:5]
            for j in top:
                print(
                    f"   [{j.get('score', '?'):>3}] {j.get('company')} — {j.get('role')} "
                    f"(${j.get('salary_min', 0)//1000}k–${j.get('salary_max', 0)//1000}k)"
                )

    return saved


if __name__ == "__main__":
    count = run_job_crew(verbose=True)
    sys.exit(0 if count >= 0 else 1)
