---
name: form-parser
description: |
  Extracts and classifies form fields from job posting pages.
  Identifies form system (Workday, Lever, Greenhouse, LinkedIn, custom HTML).
  Maps resume data to standard fields. Suggests answers for custom fields.
  Outputs JSON schema showing what the user needs to fill in.
---

# Form Parser MCP Server

> **Invoke this skill when**: Starting application to a new job, parsing a form for field extraction,
> generating a checklist of what needs to be filled, or classifying a form system type.

## Core Purpose

Parse job application forms and present the user with:
1. **What fields exist** (name, email, phone, custom questions)
2. **What's standard** (auto-fill from resume)
3. **What's custom** (needs thoughtful answer)
4. **Suggested answers** (from templates or interview prep)

Human-readable output so the user can review + copy-paste into the form.

## Supported Form Systems

### Tier 1 (Most Common)
- **Workday** (40% of enterprise tech jobs)
  - Detected by: `wd5.myworkdayjobs.com`, Workday CSS classes
  - Fields: Standard form + custom questions
  - Submit: JavaScript-based form submit

- **Lever** (20% of startups/scale-ups)
  - Detected by: `lever.co/careers`, Lever CSS
  - Fields: Clean, organized form structure
  - Submit: JSON API

- **Greenhouse** (15% of high-growth companies)
  - Detected by: `greenhouse.io`, Greenhouse CSS
  - Fields: Multi-step forms common
  - Submit: Form or API

### Tier 2 (Secondary)
- **Ashby** (5%, growing)
- **LinkedIn Apply** (5%)
- **Custom HTML** (15%, varies by company)
- **Bamboo** (for some companies)

## Field Classification

### Standard Fields (Auto-fill from profile.yaml `identity` + `answers`)
```
First Name          → identity.first_name   (e.g., Alex)
Last Name           → identity.last_name    (e.g., Example)
Email               → identity.email        (e.g., alex@example.com)
Phone               → identity.phone        (e.g., +1-555-555-0100)
Country             → identity.country      (e.g., United States)
Years of Experience → answers.years_experience
Resume/CV           → (upload your resume PDF)
LinkedIn Profile    → identity.linkedin
GitHub              → identity.github
```

### Custom Fields (Needs answer — from profile.yaml `answers` + `narrative`)
```
1. "Tell us about you" (textarea)
   └─ Suggested answer: answers.about_you

2. "Why are you excited about this role?" (textarea)
   └─ Suggested answer: answers.why_interested + company research

3. "Tell us about a project you're proud of" (textarea)
   └─ Suggested answer: answers.proudest_project

4. "What experience do you have with X?" (text/dropdown)
   └─ Suggested answer: Map from narrative.work_history highlights

5. "How many years of X technology?" (dropdown)
   └─ Suggested answer: Extract from narrative.tech_summary
```

## Output Format

### Human-Readable Form Presentation
```
╔════════════════════════════════════════════════════════════════╗
║  EXAMPLE CORP — Senior Engineer, Remote                       ║
║  https://examplecorp.wd5.myworkdayjobs.com/...                ║
║  Form System: Workday                                         ║
╚════════════════════════════════════════════════════════════════╝

STANDARD FIELDS (Auto-filled from profile.yaml)
─────────────────────────────────────────────────────────────────
✓ First Name: Alex
✓ Last Name: Example
✓ Email: alex@example.com
✓ Phone: +1-555-555-0100
✓ Country: United States
✓ Years of Experience: 10
✓ Resume: (your resume PDF)
✓ LinkedIn: linkedin.com/in/alex-example

CUSTOM FIELDS (You decide, we suggest answers)
─────────────────────────────────────────────────────────────────

[1] "Tell us about yourself" (textarea, required)
    ─────────────────────────────────────────────────────────
    SUGGESTED ANSWER:  (from profile.yaml answers.about_you)

    "I'm a software engineer with 10 years of experience building
    backend systems. Most recently at Example Corp I built the
    order-processing pipeline and mentored a team of junior engineers."

    [COPY] [EDIT] [APPROVE]

[2] "Why are you excited about this role?" (textarea, required)
    ─────────────────────────────────────────────────────────
    SUGGESTED ANSWER:  (from answers.why_interested + company research)

    "This role combines backend systems at scale with a product I
    admire. I'm eager to contribute while continuing to grow as an
    engineer."

    [COPY] [EDIT] [APPROVE]

[3] "What experience do you have with Apache Spark?" (dropdown)
    ─────────────────────────────────────────────────────────
    OPTIONS: Not familiar | Some knowledge | Professional experience | Expert

    SUGGESTED: (matched against narrative.tech_summary)

    [SELECT] [EDIT]

[4] "Tell us about a project you're proud of" (textarea)
    ─────────────────────────────────────────────────────────
    SUGGESTED ANSWER:  (from answers.proudest_project)

    "The order-processing pipeline at Example Corp — designed for
    99.99% uptime and processing 1M requests/day."

    [COPY] [EDIT] [APPROVE]

═════════════════════════════════════════════════════════════════════

SUMMARY
─────────────────────────────────────────────────────────────────
Standard fields: 8 (pre-filled, 2 min to review)
Custom fields: 4 (need answers, 5–10 min with suggestions)
Total time: ~10–15 minutes to complete form

STATUS: Ready for user review + approval
```

### JSON Schema Output (For automation)
```json
{
  "job_url": "https://examplecorp.wd5.myworkdayjobs.com/...",
  "form_system": "workday",
  "company": "Example Corp",
  "role": "Senior Engineer",
  "fields": [
    {
      "name": "firstName",
      "label": "First Name",
      "type": "text",
      "required": true,
      "auto_fill": "from_profile",
      "value": "Alex"
    },
    {
      "name": "tell_us_about_you",
      "label": "Tell us about yourself",
      "type": "textarea",
      "required": true,
      "auto_fill": false,
      "suggested_answer": "I'm a software engineer with...",
      "suggested_source": "profile.yaml answers.about_you",
      "needs_review": true
    },
    ...
  ],
  "estimated_time_minutes": 10
}
```

## Implementation

### Technology Stack
- **Playwright** or **Selenium** (load JavaScript-heavy forms)
- **BeautifulSoup** (parse HTML structure)
- **JavaScript form detection** (identify form type by CSS classes, HTML attributes)
- **Python regex** (classify question types)

### Form Detection Logic

```python
def detect_form_system(page_html, url):
    if 'wd5.myworkdayjobs.com' in url:
        return 'workday'
    elif 'lever.co' in url:
        return 'lever'
    elif 'greenhouse.io' in url:
        return 'greenhouse'
    elif soup.find('form[data-form-id]'):  # Ashby signature
        return 'ashby'
    else:
        return 'custom_html'

def classify_field_type(field_element, field_label):
    if is_standard_field(field_label):  # Heuristic match
        return 'standard'
    elif field_type in ['textarea', 'rich_text']:
        return 'custom_answer'
    elif field_type == 'select':
        return 'custom_choice'
    else:
        return 'custom_text'
```

### Answer Suggestion Logic

```
1. For "Tell us about you" → profile.yaml answers.about_you
2. For "Why this company?" → profile.yaml answers.why_interested + company research
3. For "Project you're proud of" → profile.yaml answers.proudest_project
4. For "Experience with X?" → Map to narrative.work_history highlights
5. For "Years of X?" → Extract from narrative.tech_summary / answers.years_experience
```

## Configuration

```json
{
  "form_systems": {
    "workday": {
      "selectors": {
        "form": "form[data-automation-id='form']",
        "field": "input, textarea, select",
        "label": "label"
      },
      "js_wait_time": 3000
    },
    "lever": {
      "selectors": {
        "form": ".application-form",
        "field": "input, textarea, select"
      },
      "js_wait_time": 2000
    }
  },
  "standard_fields": [
    "first name", "last name", "email", "phone", "country",
    "years of experience", "resume", "linkedin", "github"
  ],
  "answer_templates": {
    "tell_us_about_you": "cover-letter",
    "why_this_company": "cover-letter",
    "project_proud_of": "interview-prep"
  }
}
```

## Workflow

1. **Parse form** (30 sec): Extract all fields + types
2. **Classify** (10 sec): Standard vs. custom
3. **Suggest answers** (20 sec): Map templates to questions
4. **Present to the user** (1 min): Show human-readable format
5. **User reviews** (5–10 min): Copy-paste or edit answers
6. **Mark approved** (30 sec): user confirms ready to submit
7. **Submit** (via form-submit server): Send the application

Total: ~10–15 min per form

## Integration Points

| Component | Usage |
|-----------|-------|
| `job-discovery` MCP | Provides job URLs to parse |
| `cover-letter` skill | Answer suggestions for custom fields |
| `interview-prep` skill | Project examples, talking points |
| `form-submit` MCP | Receives approved form data for submission |
| `job_tracker.db` | Logs form parsing attempts |

## Success Metrics

- **Coverage**: Support >95% of job forms (Workday, Lever, Greenhouse, LinkedIn, custom)
- **Accuracy**: Correctly classify 99% of fields (standard vs. custom)
- **Time savings**: Reduce form completion from 30 min to 5–10 min per form
- **Reliability**: No parsing failures (graceful fallback to manual if needed)

## References

| File | Purpose |
|------|---------|
| `profile.yaml` (repo root) | Identity, narrative, and screening answers |
| `profile.yaml.example` | Template — copy and fill in your data |
| `src/profile_loader.py` | Loads the profile for all tools |
