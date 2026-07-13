# Eval Buckets

Behavior evals under `.github/evals/` are organized into five buckets.
Knowing which bucket a new eval belongs in is the first step the
enforcer asks for.

## `ai/` — LLM-backed surfaces

Anything that calls a model provider on user input: chatbots, generated
articles, summarization endpoints, classifier routers.

**Oracle shape:** real input fixtures + assertions against output
content (specific strings, structural invariants, hallucination probes).
**Never** assert against status codes or the model's own self-report.

Example pin: "Chatbot must not name a player as rostered unless that
player appears in `roster_players`."

## `tools/` — MCP tools

Every `@mcp.tool()` registration gets an eval that exercises it on
real data and asserts the response shape + content.

**Oracle shape:** call the tool with a known input, assert specific
fields in the returned record.

Example pin: "`sb_get_skill_score(player, season)` returns a row from
`skill_scores` for the current season — never a 0.0 default."

## `skills/` — Skill shape + project-specific skill behavior

The universal `test_skill_shape.py` lives here and gates every skill's
file layout. Project-specific skill behavior evals (e.g.
"`draft-day` returns a balanced 3-phase target list") also live here.

## `voice/` — Personas, system prompts, voice profiles

Pins the persona's voice rules against generated output. If a persona
says "never use first person," there's an eval that probes for first
person and fails on a hit.

**Oracle shape:** prompt fixtures + regex/structural assertions on
generated text.

## `ui/` — Routes and contracts

Frontend route contracts: SEO tags present, JSON-LD valid, required
components mounted exactly once. Backend route contracts: required
fields in response, auth required when expected.

**Oracle shape:** route fixtures + DOM/JSON parsing + assertions.

## When in doubt

Ask `@dom-eval-enforcer`. The agent will name the bucket, the file
path, and the rule the eval should encode.
