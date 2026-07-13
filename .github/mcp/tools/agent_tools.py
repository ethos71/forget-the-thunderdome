"""dom MCP agent delegation tools.

Delegates atomic single-file tasks to local Ollama (free) or OpenRouter (paid).
model="auto" classifies complexity first, then routes the four-tier waterfall:
  SIMPLE        → ollama/qwen   (free)
  MEDIUM        → haiku         (~$0.01)
  COMPLEX       → sonnet        (~$0.10)
  ARCHITECTURAL → opus          (~$2.00)
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

def _find_project_root() -> Path:
    """Walk up from this file until we find pyproject.toml (or .git as fallback).

    The .git fallback lets non-Python consumers (and dom itself) use
    delegate_task/ask_local + usage logging without a pyproject.toml.
    """
    p = Path(__file__).resolve()
    fallback: Path | None = None
    while p.parent != p:
        p = p.parent
        if (p / "pyproject.toml").exists():
            return p
        if fallback is None and (p / ".git").exists():
            fallback = p
    if fallback is not None:
        return fallback
    raise RuntimeError("Could not find project root (no pyproject.toml or .git found)")

_PROJECT_ROOT = _find_project_root()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Model routing — Ollama (local/free) vs OpenRouter (paid)
# ---------------------------------------------------------------------------

_OLLAMA_BASE_URL = "http://localhost:11434/v1"
_OLLAMA_DEFAULT = "qwen2.5-coder:7b"

# Aliases that route to local Ollama
_OLLAMA_ALIASES: dict[str, str] = {
    "ollama": _OLLAMA_DEFAULT,
    "qwen": "qwen2.5-coder:7b",
    "qwen-coder": "qwen2.5-coder:7b",
    "codellama": "codellama:7b",
    "deepseek": "deepseek-coder:6.7b",
    "llama-local": "llama3.1:8b",
    "llama3-local": "llama3.1:8b",
}

# Aliases that route to OpenRouter (paid). IDs verified against the live
# OpenRouter catalog 2026-07-10 (dots, not dashes — claude-sonnet-4-6 etc.
# never existed there). Tier aliases point at the cheapest current capable
# model; re-verify with .github/skills/dom-usage/scripts/check-rates.py.
_OPENROUTER_ALIASES: dict[str, str] = {
    "haiku": "anthropic/claude-haiku-4.5",
    "haiku-4": "anthropic/claude-haiku-4.5",
    "sonnet": "anthropic/claude-sonnet-5",      # $2/$10 — cheaper AND newer than 4.6
    "sonnet-4": "anthropic/claude-sonnet-4.6",
    "opus": "anthropic/claude-opus-4.8",
    "opus-4": "anthropic/claude-opus-4.7",
    "llama": "meta-llama/llama-3.3-70b-instruct",
    "llama3": "meta-llama/llama-3.3-70b-instruct",
    "gemini-flash": "google/gemini-2.5-flash-lite",
}


# ---------------------------------------------------------------------------
# Usage accounting — every real model call appends one JSONL record so the
# `/usage` skill can report tokens-per-model and audit Ollama enforcement.
# Ollama (local) is free; OpenRouter rates below are ESTIMATES in USD per 1M
# tokens (input, output) — edit them to match your plan. Keyed by substring
# of the resolved model id.
# ---------------------------------------------------------------------------

# First substring match wins — keep specific keys before generic ones.
# Live-verified 2026-07-10 (opus-4.5+ is $5/$25, NOT the old $15/$75).
_OPENROUTER_RATES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus": (5.0, 25.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
    "llama-3.3-70b": (0.10, 0.32),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}


def _usage_log_path() -> Path:
    """Resolve the usage-log path (env override wins, else <root>/.dom/usage.jsonl)."""
    override = os.environ.get("DOM_USAGE_LOG")
    if override:
        return Path(override)
    return _PROJECT_ROOT / ".dom" / "usage.jsonl"


def _estimate_cost(model_id: str, backend: str, prompt_toks: int, completion_toks: int):
    """Estimated USD cost. 0.0 for local Ollama; None when the rate is unknown."""
    if backend == "ollama":
        return 0.0
    for key, (rate_in, rate_out) in _OPENROUTER_RATES.items():
        if key in model_id:
            return round(prompt_toks / 1e6 * rate_in + completion_toks / 1e6 * rate_out, 6)
    return None


def _log_usage(record: dict) -> None:
    """Append one usage record as a JSON line. Best-effort — never raises."""
    try:
        path = _usage_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass  # silent-ok: best-effort — must not break the caller


def _record_call(
    *,
    requested: str,
    model_id: str,
    backend: str,
    complexity: str | None,
    ollama_up: bool,
    response,
    purpose: str = "delegation",
    latency_s: float | None = None,
) -> None:
    """Extract token usage from an OpenAI-compatible response and log it.

    purpose: "delegation" (a real code task), "routing" (the local
    classifier call), or "adhoc" (ask_local Q&A). latency_s is wall-clock
    seconds for the API call — the cost-vs-time half of the /usage report.
    """
    usage = getattr(response, "usage", None)
    prompt_toks = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_toks = int(getattr(usage, "completion_tokens", 0) or 0)
    total_toks = int(getattr(usage, "total_tokens", prompt_toks + completion_toks) or 0)
    _log_usage({
        "ts": datetime.now(timezone.utc).isoformat(),
        "purpose": purpose,
        "requested": requested,
        "model": model_id,
        "backend": backend,
        "complexity": complexity,
        "ollama_up": ollama_up,
        "prompt_tokens": prompt_toks,
        "completion_tokens": completion_toks,
        "total_tokens": total_toks,
        "latency_s": round(latency_s, 2) if latency_s is not None else None,
        "est_cost_usd": _estimate_cost(model_id, backend, prompt_toks, completion_toks),
    })


@contextmanager
def _abort_logged(
    *,
    requested: str,
    model_id: str,
    backend: str,
    complexity: str | None,
    ollama_up: bool,
    purpose: str,
    t0: float,
):
    """Log an abort row if the process is killed mid-model-call.

    A foreground shell timeout (e.g. a 120s cap) TERMs the process while a
    slow local model is mid-generation; without this the call vanishes from
    the usage log entirely (@smartballz field report, 2026-07-10). Catches
    SIGTERM/SIGINT/SIGHUP, writes the row with partial latency, then re-raises
    the signal's default behavior. SIGKILL cannot be caught — those still
    vanish. No-ops safely outside the main thread.
    """
    def _handler(signum, frame):
        _log_usage({
            "ts": datetime.now(timezone.utc).isoformat(),
            "purpose": purpose,
            "requested": requested,
            "model": model_id,
            "backend": backend,
            "complexity": complexity,
            "ollama_up": ollama_up,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_s": round(time.monotonic() - t0, 2),
            "est_cost_usd": _estimate_cost(model_id, backend, 0, 0),
            "aborted": True,
            "abort_signal": signal.Signals(signum).name,
        })
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)  # chain to the default (terminate)

    prev: dict = {}
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            prev[sig] = signal.signal(sig, _handler)
        except (ValueError, OSError):  # silent-ok: non-main thread — guard unavailable
            pass
    try:
        yield
    finally:
        for sig, h in prev.items():
            try:
                signal.signal(sig, h)
            except (ValueError, OSError):  # silent-ok: restore is best-effort
                pass


def _ollama_status() -> tuple[bool, list[str]]:
    """Return (is_running, installed_model_names)."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return True, models
    except Exception:
        return False, []


# SHAPE RULE (from @smartballz field data, 2026-07-10): local free-tier models
# reliably land ONE single-line/single-hunk mechanical edit but fail multi-line
# prose/comment restructures even when conceptually trivial — so shape, not
# conceptual difficulty, decides SIMPLE vs MEDIUM.
_ROUTER_SYSTEM = """\
You are a task complexity classifier for a code assistant routing system.
Classify the given coding task as exactly one of: SIMPLE, MEDIUM, COMPLEX, or ARCHITECTURAL.

SIMPLE:        ONE single-line (or single small hunk) mechanical change in one file — rename a symbol, fix a typo, update one constant/string, toggle a flag. If the edit touches multiple lines, multiple regions, or rewrites prose/comments/headers, it is NOT SIMPLE.
MEDIUM:        Still ONE file: add a function, write a test, small feature, refactor one function, fix a logic bug — or ANY multi-line rewrite/restructure of comments/headers/docstrings/prose in that file, even when conceptually trivial.
COMPLEX:       MULTIPLE files, or debugging a subtle multi-step issue, or changing behavior across a single subsystem. A single-file edit is never COMPLEX.
ARCHITECTURAL: Cross-system design, deep planning, migration that spans subsystems, hard debug requiring whole-codebase reasoning.

Examples:
- "Rename port to server_port in auth.py" -> SIMPLE
- "Rewrite the 12-line header comment in deploy.sh" -> MEDIUM
- "Add a retry helper function to client.py" -> MEDIUM
- "Refactor JWT handling across the auth module's 4 files" -> COMPLEX

Respond with ONLY the single word: SIMPLE, MEDIUM, COMPLEX, or ARCHITECTURAL.
"""


def _classify_task(
    change: str, files: list[str], status: tuple[bool, list[str]] | None = None
) -> tuple[str, str]:
    """Classify task complexity using local Ollama. Returns (complexity, model_to_use).

    Falls back to MEDIUM/haiku if Ollama is not running. Pass `status` (a
    prefetched `_ollama_status()` result) to avoid a redundant probe.
    """
    running, installed = status if status is not None else _ollama_status()
    if not running:
        return "MEDIUM", "haiku"

    # Pick fastest available local model for routing (smallest wins)
    router_model = next(
        (m for m in ["llama3.2:3b", "llama3.1:8b", "qwen2.5-coder:7b"] if any(m.split(":")[0] in i for i in installed)),
        None,
    )
    if not router_model:
        return "MEDIUM", "haiku"

    prompt = f"Task: {change}\nFiles: {', '.join(files)}"
    try:
        from openai import OpenAI  # noqa: PLC0415
        client = OpenAI(base_url=_OLLAMA_BASE_URL, api_key="ollama")
        t0 = time.monotonic()
        resp = client.chat.completions.create(
            model=router_model,
            messages=[
                {"role": "system", "content": _ROUTER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=5,
        )
        # The classifier is itself free local work — log it so /usage shows
        # the true routing overhead (tokens + seconds).
        _record_call(
            requested="auto", model_id=router_model, backend="ollama",
            complexity=None, ollama_up=True, response=resp,
            purpose="routing", latency_s=time.monotonic() - t0,
        )
        verdict = (resp.choices[0].message.content or "").strip().upper()
        # Order matters: ARCHITECTURAL contains COMPLEX-like patterns, check it first.
        for word in ("ARCHITECTURAL", "COMPLEX", "MEDIUM", "SIMPLE"):
            if word in verdict:
                verdict = word
                break
        else:
            verdict = "MEDIUM"
    except Exception:
        verdict = "MEDIUM"

    model_map = {
        "SIMPLE": "ollama",
        "MEDIUM": "haiku",
        "COMPLEX": "sonnet",
        "ARCHITECTURAL": "opus",
    }
    return verdict, model_map.get(verdict, "haiku")

_SYSTEM_PROMPT = """\
You are a surgical code editor. Output ONLY a JSON array. No prose, no markdown fences, no explanation.

EXAMPLE — adding a docstring to a function:
Input file contains:
  def add(a, b):
      return a + b

Output:
[{"file": "math.py", "old": "def add(a, b):\n    return a + b", "new": "def add(a, b):\n    \"\"\"Add two numbers.\"\"\"\n    return a + b"}]

RULES:
1. "old" must be an EXACT copy of characters from the file — never empty string
2. "new" is the replacement for exactly those characters
3. Minimal change — only touch what is asked
4. If no change needed: []
5. Output ONLY the JSON array — nothing before or after it
"""

_TASK_TEMPLATE = """\
TASK:
{change}

FILES:
{file_contents}

TEST COMMAND (for reference only — do not include in output):
{test}
"""


def _load_env() -> dict[str, str]:
    """Load .env from project root if available."""
    env_path = _PROJECT_ROOT / ".env"
    env: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def delegate_task(
    files: list[str],
    change: str,
    test: str,
    model: str = "auto",
    dry_run: bool = False,
) -> dict:
    """Delegate an atomic code change to a local or remote model.

    model="auto" (default) classifies complexity first, then routes the
    four-tier waterfall:
      SIMPLE        → ollama/qwen (free/local)
      MEDIUM        → haiku (~$0.01)
      COMPLEX       → sonnet (~$0.10)
      ARCHITECTURAL → opus (~$2.00)

    Args:
        files: Relative paths to file(s) to read and potentially modify.
        change: Plain-English description of what to change.
        test: Shell command to run after applying edits to verify success.
        model: 'auto' (default), 'ollama' (force free), 'haiku', 'sonnet',
               'opus', or full ID.
        dry_run: If True, return the plan without applying edits or running tests.

    Returns dict with keys: status, model, backend, complexity, edits_applied, test_output, error.
    """
    try:
        from openai import OpenAI  # noqa: PLC0415
    except ImportError:
        return {"status": "error", "error": "openai package not installed — run: poetry add openai"}

    # ── Auto-routing ─────────────────────────────────────────────────────────
    requested_model = model  # what the caller asked for, before resolution
    ollama_up, ollama_models = _ollama_status()  # probe once, reuse below
    complexity: str | None = None
    if model == "auto":
        complexity, model = _classify_task(change, files, status=(ollama_up, ollama_models))

    # Loud fallback — silent paid routing was enforcement gap #2. The log
    # already records ollama_up:false; surface it to the CALLER too.
    fallback_warning: str | None = None
    if requested_model == "auto" and not ollama_up:
        fallback_warning = (
            "Ollama is DOWN — auto-router fell back to PAID "
            f"'{model}'. Start `ollama serve` to keep the free tier available."
        )

    # ── Determine backend and model ID ──────────────────────────────────────
    use_ollama = (
        model in _OLLAMA_ALIASES
        or model.startswith("ollama/")
        or model == "ollama"
    )

    if use_ollama:
        if model.startswith("ollama/"):
            model_id = model[len("ollama/"):]
        else:
            model_id = _OLLAMA_ALIASES.get(model, _OLLAMA_DEFAULT)

        running, installed = ollama_up, ollama_models
        if not running:
            return {
                "status": "error",
                "error": "Ollama not running. Start it with: ollama serve",
                "hint": f"Then pull the model: ollama pull {model_id}",
            }
        # Allow partial match (e.g. "qwen2.5-coder:7b" matches "qwen2.5-coder:7b-q4_K_M")
        if not any(model_id.split(":")[0] in m for m in installed):
            # Auto-fallback to llama3.1:8b (general LLM — works for simple edits,
        # unreliable on Python syntax like triple-quotes). Run `sbz-pull` for best results.
            if any("llama3.1" in m for m in installed):
                model_id = "llama3.1:8b"
                # caller will see model_id changed — warn via dry_run or result
            else:
                return {
                    "status": "error",
                    "error": f"Model '{model_id}' not installed locally.",
                    "hint": "Run: sbz-pull  (installs qwen2.5-coder:7b, recommended for code)",
                    "installed": installed,
                }
        backend = "ollama"
        client = OpenAI(base_url=_OLLAMA_BASE_URL, api_key="ollama")
    else:
        model_id = _OPENROUTER_ALIASES.get(model, model)
        env = _load_env()
        api_key = env.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            return {"status": "error", "error": "OPENROUTER_API_KEY not found in .env"}
        backend = "openrouter"
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={"X-Title": "SmartBallz MCP"},
        )

    # ── Read file contents ───────────────────────────────────────────────────
    file_contents_parts: list[str] = []
    for rel_path in files:
        path = _PROJECT_ROOT / rel_path
        if not path.exists():
            return {"status": "error", "error": f"File not found: {rel_path}"}
        content = path.read_text(encoding="utf-8")
        file_contents_parts.append(f"--- {rel_path} ---\n{content}")

    file_contents = "\n\n".join(file_contents_parts)
    user_message = _TASK_TEMPLATE.format(
        change=change,
        file_contents=file_contents,
        test=test,
    )

    if dry_run:
        return {
            "status": "dry_run",
            **({"warning": fallback_warning} if fallback_warning else {}),
            "complexity": complexity,
            "model": model_id,
            "backend": backend,
            "files": files,
            "change": change,
            "test": test,
            "prompt_chars": len(user_message),
            "cost": (
                "FREE" if backend == "ollama"
                else "~$0.01" if "haiku" in model_id
                else "~$2.00" if "opus" in model_id
                else "~$0.10"  # sonnet / default OpenRouter paid
            ),
        }

    # ── Call model ───────────────────────────────────────────────────────────
    t0 = time.monotonic()
    try:
        with _abort_logged(
            requested=requested_model, model_id=model_id, backend=backend,
            complexity=complexity, ollama_up=ollama_up, purpose="delegation", t0=t0,
        ):
            response = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
                max_tokens=4096,
            )
    except Exception as e:
        return {"status": "error", "error": f"{backend} API error: {e}"}

    # Record token usage the moment the call succeeds — before any edit-parsing
    # can bail out — so `/usage` sees every real token that hit a model.
    _record_call(
        requested=requested_model,
        model_id=model_id,
        backend=backend,
        complexity=complexity,
        ollama_up=ollama_up,
        response=response,
        purpose="delegation",
        latency_s=time.monotonic() - t0,
    )

    raw = response.choices[0].message.content or ""

    # Parse JSON edits
    # Strip accidental markdown fences if model ignores instructions
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]

    try:
        edits: list[dict] = json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "error": "Model returned non-JSON response",
            "raw_response": raw[:500],
        }

    if not isinstance(edits, list):
        return {
            "status": "error",
            "error": "Model returned non-list JSON",
            "raw_response": raw[:500],
        }

    if len(edits) == 0:
        return {
            "status": "no_changes",
            "model": model_id,
            "message": "Model determined no changes were needed.",
        }

    # Apply edits
    applied: list[dict] = []
    errors: list[str] = []

    for edit in edits:
        rel_path = edit.get("file", "")
        old_str = edit.get("old", "")
        new_str = edit.get("new", "")

        if not rel_path or not old_str:
            errors.append(f"Malformed edit (empty 'old'): {json.dumps(edit)[:120]}")
            continue

        path = _PROJECT_ROOT / rel_path
        if not path.exists():
            errors.append(f"File not found for edit: {rel_path}")
            continue

        content = path.read_text(encoding="utf-8")
        if old_str not in content:
            errors.append(f"old string not found in {rel_path}: {old_str[:80]!r}...")
            continue

        path.write_text(content.replace(old_str, new_str, 1), encoding="utf-8")
        applied.append({"file": rel_path, "chars_changed": len(new_str) - len(old_str)})

    if errors:
        return {
            "status": "partial_failure",
            **({"warning": fallback_warning} if fallback_warning else {}),
            "complexity": complexity,
            "model": model_id,
            "backend": backend,
            "edits_applied": applied,
            "errors": errors,
        }

    # ── Run test ─────────────────────────────────────────────────────────────
    test_result = subprocess.run(
        test,
        shell=True,  # nosec B602 — test cmd is operator/agent-provided by design
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    test_passed = test_result.returncode == 0
    test_output = (test_result.stdout + test_result.stderr).strip()

    return {
        "status": "success" if test_passed else "test_failed",
        **({"warning": fallback_warning} if fallback_warning else {}),
        "complexity": complexity,
        "model": model_id,
        "backend": backend,
        "edits_applied": applied,
        "test_passed": test_passed,
        "test_returncode": test_result.returncode,
        "test_output": test_output[:1000],
    }


def ask_local(
    question: str,
    model: str = "llama3.2:3b",
    system: str | None = None,
    max_tokens: int = 1024,
) -> dict:
    """Free local Q&A via Ollama, logged to the usage log (purpose='adhoc').

    Use this instead of a paid model for anything a small local model can
    answer: summaries, classifications, drafts, quick reviews. Unlike the
    shell `ask` helper, calls made here show up in the /usage report with
    tokens + latency, so the savings are measurable.
    """
    try:
        from openai import OpenAI  # noqa: PLC0415
    except ImportError:
        return {"status": "error", "error": "openai package not installed — run: pip install openai"}

    running, installed = _ollama_status()
    if not running:
        return {"status": "error", "error": "Ollama not running. Start it with: ollama serve"}

    model_id = _OLLAMA_ALIASES.get(model, model)
    if not any(model_id.split(":")[0] in m for m in installed):
        return {
            "status": "error",
            "error": f"Model '{model_id}' not installed locally.",
            "installed": installed,
        }

    client = OpenAI(base_url=_OLLAMA_BASE_URL, api_key="ollama")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": question})

    t0 = time.monotonic()
    try:
        with _abort_logged(
            requested=model, model_id=model_id, backend="ollama",
            complexity=None, ollama_up=True, purpose="adhoc", t0=t0,
        ):
            response = client.chat.completions.create(
                model=model_id, messages=messages, temperature=0.2, max_tokens=max_tokens,
            )
    except Exception as e:
        return {"status": "error", "error": f"ollama API error: {e}"}
    latency = time.monotonic() - t0

    _record_call(
        requested=model, model_id=model_id, backend="ollama",
        complexity=None, ollama_up=True, response=response,
        purpose="adhoc", latency_s=latency,
    )
    return {
        "status": "success",
        "model": model_id,
        "latency_s": round(latency, 2),
        "answer": response.choices[0].message.content or "",
    }


def get_context() -> dict:
    """Return a compact project context snapshot for session bootstrap.

    Replaces reading MEMORY.md + CLAUDE.md + git status separately.
    Returns git state, active plan summary, leagues, key paths, and memory index.
    """
    result: dict = {}

    # Git state
    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            cwd=str(_PROJECT_ROOT), capture_output=True, text=True, timeout=10,
        )
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(_PROJECT_ROOT), capture_output=True, text=True, timeout=10,
        )
        result["git_log"] = log.stdout.strip()
        result["git_status"] = status.stdout.strip()
        result["git_branch"] = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(_PROJECT_ROOT), capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception as e:
        result["git_error"] = str(e)

    # Active plan (most recent .md in .claude/plans/)
    try:
        plans_dir = Path.home() / ".claude" / "plans"
        if plans_dir.exists():
            plans = sorted(plans_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if plans:
                plan_text = plans[0].read_text(encoding="utf-8")
                # First 40 lines capture title + context + phase overview
                result["active_plan"] = "\n".join(plan_text.splitlines()[:40])
                result["active_plan_file"] = plans[0].name
    except Exception:
        pass  # silent-ok: best-effort — must not break the caller

    # Memory index
    try:
        memory_index = _PROJECT_ROOT / "docs" / "robots" / "MEMORY.md"
        if not memory_index.exists():
            memory_index = Path.home() / ".claude" / "projects" / \
                "-home-dominick-workspace-smartballz" / "memory" / "MEMORY.md"
        if memory_index.exists():
            result["memory_index"] = memory_index.read_text(encoding="utf-8")[:1500]
    except Exception:
        pass  # silent-ok: best-effort — must not break the caller

    # Static constants (avoids reading CLAUDE.md every session)
    result["constants"] = {
        "leagues": [
            {"name": "Monster Island #6273", "league_id": 24, "format": "14-cat H2H Auction $320"},
            {"name": "Steamboat Willie #53605", "league_id": 25, "format": "14-cat H2H Snake"},
        ],
        "primary_user": "ethos71",
        "prod_port": 8501,
        "dev_port": 8080,
        "react_dev_port": 5173,
        "db_path": "data/smartballz.db",
        "scoring": "H=1,2B=2,3B=3,HR=4,R=1,RBI=1,SB=2,BB=1",
    }

    # Tool reference location
    result["tool_reference"] = ".github/mcp/TOOL_REFERENCE.md"

    return result
