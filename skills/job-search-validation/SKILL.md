---
name: job-search-validation
description: >-
  How to validate a job posting URL before adding it to the pipeline or
  recommending it to the user. Built from real failures during search
  sessions — HTTP 200 ≠ active posting, and most ATS systems serve
  empty pages to scrapers.
---

# Job Search Validation

The single biggest source of frustration during a search session
is recommending dead links and stale postings. This skill encodes what works.

## The core rule

**HTTP 200 does NOT mean the posting is active.** Many ATS systems serve a
"this job is no longer active" page with a 200 status. Examples confirmed
in the wild:

- The Hershey Company (`careers.thehersheycompany.com`) — returns 200 + "This job posting is no longer active"
- Lincoln Financial (`jobs.lincolnfinancial.com`) — returns 200 + "This position is no longer posted"
- UPMC (`careers.upmc.com`) — returns 200 + "Job not found - UPMC" as the page title
- Vanguard (`vanguardjobs.com`) — returns 200 + "Page not found - Vanguard Careers" for stale IDs

**You must read the page content** (the actual job title, description, or
the absence of "no longer active" / "not found" language) to validate.

## Validation hierarchy (fast → slow)

### Tier 1: curl + title-and-body grep
Fast batch validation. Use this for screening ~20 URLs at once.

```bash
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
URL="..."
body=$(curl -A "$UA" -L -s --max-time 12 "$URL")
title=$(echo "$body" | grep -oE '<title>[^<]+' | head -1 | sed 's|<title>||')

if echo "$body" | grep -qiE 'no longer (active|posted|available|accepting)|position is closed|job has been (closed|filled)|posting (has expired|is closed)|requisition is no longer|job not found|page not found|expired'; then
  echo "❌ CLOSED | $title"
elif echo "$title" | grep -qiE 'not found|page not found|expired'; then
  echo "❌ NOT FOUND | $title"
elif [ -n "$title" ]; then
  echo "✅ LIKELY OPEN | $title"
else
  echo "❓ NEED MANUAL CHECK | (empty title — JS-rendered ATS)"
fi
```

### Tier 2: WebFetch with explicit content prompt
Use when curl returns empty title (JS-rendered) OR to confirm Tier 1 hits
before recommending.

```
WebFetch(
  url: "...",
  prompt: "Is this an active, currently-open job posting? Or does the page say
           'no longer active', 'this job is closed', 'this position has been
           filled', or redirect to a generic page? Quote the relevant text."
)
```

### Tier 3: Browser only
Workday-based ATS (`*.wd5.myworkdayjobs.com`) and dejobs.org are heavily
JS-rendered. Neither curl nor WebFetch can read the job content. Either:
- Hand the link to the user to verify in browser, OR
- Pull the same role from a Greenhouse/LinkedIn mirror if one exists

## ATS reliability ranking

| ATS / host | Reliability | Validation method |
|---|---|---|
| **Greenhouse** (`job-boards.greenhouse.io`, `boards.greenhouse.io`) | ⭐⭐⭐⭐⭐ | WebFetch reads content reliably |
| **Direct ATS** (Lockheed, Erie Insurance, Hershey, Lincoln Financial) | ⭐⭐⭐⭐ | Tier 1 works — read body for "no longer" patterns |
| **LinkedIn** (`linkedin.com/jobs/view/{id}`) | ⭐⭐⭐ | Rate-limited; same URL returns different content per call. Newer job IDs (43xxxxxxxx+) more likely fresh; older (38xxxxxxxx) usually stale. Use WebFetch with retry. |
| **Ashby** (`jobs.ashbyhq.com`) | ⭐⭐⭐ | WebFetch sometimes returns minimal content |
| **Workday** (`*.wd5.myworkdayjobs.com`) | ⭐ | JS-rendered, scraper-blind. Browser only. |
| **dejobs.org** | ⭐ | JS-rendered aggregator. Browser only. |
| **JS-rendered company sites** (Northrop, UPMC newer pages) | ⭐ | Browser only |

## LinkedIn job ID heuristic

LinkedIn job IDs are auto-incrementing integers. Rough freshness signal:

- `43xxxxxxxx` and `44xxxxxxxx` → posted 2026, likely fresh
- `42xxxxxxxx` → late 2025, possibly fresh
- `40xxxxxxxx`–`41xxxxxxxx` → mid 2025, mixed
- `38xxxxxxxx` and below → 2024 or earlier, usually closed and redirects to generic search

When LinkedIn redirects a closed job, the page title becomes something like:
`"7,000+ Senior Product Design Engineer jobs in United States"` or
`"813 Klaviyo jobs in United States"` (a generic search result). That title
pattern is the dead-job signal.

A live LinkedIn job has a title like:
`"Stanley Black & Decker, Inc. hiring Lead Engineer, Embedded Software in Towson, MD | LinkedIn"`

The presence of `" hiring "` in the title is the alive marker.

## Recommendation rules

Before handing a list of links to the user:

1. **Every link must be content-validated**, not HTTP-status-validated
2. **State the validation method per link** in the response (e.g., "WebFetch confirmed", "browser-only — couldn't validate")
3. **Never pad a list with unverified URLs** — fewer real links beats more padded ones
4. **If you can't validate ≥20 links**, give the user fewer and link to live search pages instead
5. **Re-check the day of application** — postings expire fast in this market

## Sanity checks before adding to the pipeline

- [ ] URL returns active posting content (Tier 1 or Tier 2 verified)
- [ ] Role matches the profile's `search.target_roles`
- [ ] Company is not on the user's exclusion list (if they keep one)
- [ ] Location is remote (if `search.remote_only`) OR matches `search.locations`
- [ ] Salary meets `search.min_salary` (if posted)
- [ ] If LinkedIn URL: job ID is in the recent range OR WebFetch confirmed "hiring" in title

All criteria come from `profile.yaml` — see `profile.yaml.example` at the repo root.
