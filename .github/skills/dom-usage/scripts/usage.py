#!/usr/bin/env python3
"""dom usage — token/cost/latency report + Ollama-enforcement audit.

Reads the usage log written by `delegate_task` / `ask_local`
(.dom/usage.jsonl by default) and answers:

  1. What tokens went to what models?      → per-model table + totals
  2. Is Ollama being enforced correctly?   → free/paid split + violations
  3. What did Ollama save us?              → same tokens priced at paid tiers
  4. What did the savings cost in time?    → measured latency, $/minute tradeoff

Each log line is one real model call:
  {"ts": "...", "purpose": "delegation|routing|adhoc", "requested": "auto",
   "model": "qwen2.5-coder:7b", "backend": "ollama", "complexity": "SIMPLE",
   "ollama_up": true, "prompt_tokens": 812, "completion_tokens": 143,
   "total_tokens": 955, "latency_s": 6.4, "est_cost_usd": 0.0}

Usage:
  usage.py [--log PATH] [--since DAYS] [--json] [--md]

Exit code is 0 on a clean audit, 1 when hard enforcement violations exist,
so it can gate CI.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Which complexity tiers the routing contract says MUST run free/local.
# (docs/routing-guide.md → SIMPLE → Ollama/qwen, free.)
_FREE_TIERS = {"SIMPLE"}

# USD per 1M tokens (input, output) — mirror of _OPENROUTER_RATES in
# agent_tools.py (live-verified 2026-07-10; re-check with check-rates.py).
# Used to price what free Ollama tokens WOULD have cost at each tier alias.
_RATES = {
    "opus": (5.0, 25.0),
    "sonnet": (2.0, 10.0),
    "haiku": (1.0, 5.0),
}

# Reference paid-model latency (seconds/call) used for the cost-vs-time
# tradeoff ONLY when the log has no measured paid calls to compare against.
# Source: docs/routing-guide.md cost table (Haiku 5-10s → midpoint 8s).
_PAID_REF_LATENCY_S = 8.0


def _find_log(explicit: str | None) -> Path:
    """Resolve the usage-log path: --log > $DOM_USAGE_LOG > <project-root>/.dom/usage.jsonl."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("DOM_USAGE_LOG")
    if env:
        return Path(env).expanduser()
    p = Path.cwd().resolve()
    for cand in [p, *p.parents]:
        if (cand / ".dom" / "usage.jsonl").exists():
            return cand / ".dom" / "usage.jsonl"
        if (cand / "pyproject.toml").exists() or (cand / ".git").exists():
            return cand / ".dom" / "usage.jsonl"
    return p / ".dom" / "usage.jsonl"


def _bot_log(bot: str) -> Path:
    """Resolve ANOTHER bot's usage log via the registry — powers `dom usage --bot X`
    (e.g. @dom pulling @smartballz's report). Bot repos live under the workspace
    root: $DOM_WORKSPACE, else the dom repo's parent dir (same as delegate.py)."""
    import json
    here = Path.cwd().resolve()
    root = next((c for c in [here, *here.parents]
                 if (c / ".github" / "dom-bots.json").exists()), None)
    if root is None:
        raise SystemExit("--bot needs .github/dom-bots.json (run from a dom-installed repo)")
    reg = json.loads((root / ".github" / "dom-bots.json").read_text(encoding="utf-8"))
    ws_env = os.environ.get("DOM_WORKSPACE")
    workspace = Path(ws_env).expanduser() if ws_env else (root / reg.get("workspace_default", "..")).resolve()
    b = reg.get("bots", {}).get(bot)
    if not b:
        raise SystemExit(f"unknown bot '{bot}' — known: {', '.join(sorted(reg.get('bots', {})))}")
    return workspace / b["dir"] / ".dom" / "usage.jsonl"


def _load(path: Path, since_days: float | None) -> list[dict]:
    if not path.exists():
        return []
    cutoff = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # skip a corrupt line rather than crash the report
        if cutoff is not None:
            try:
                ts = datetime.fromisoformat(rec.get("ts", ""))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
            except (ValueError, TypeError):
                pass  # undated/garbled ts → keep it, don't silently drop spend
        rows.append(rec)
    return rows


def _aggregate(rows: list[dict]) -> dict:
    per_model: dict[str, dict] = {}
    purposes: dict[str, int] = {}
    tot = {"tokens": 0, "prompt": 0, "completion": 0, "cost": 0.0}
    cost_known = True
    free = {"calls": 0, "prompt": 0, "completion": 0, "tokens": 0, "time_s": 0.0, "timed": 0}
    paid = {"calls": 0, "prompt": 0, "completion": 0, "tokens": 0, "time_s": 0.0, "timed": 0}

    for r in rows:
        model = r.get("model", "?")
        backend = r.get("backend", "?")
        pt = int(r.get("prompt_tokens", 0) or 0)
        ct = int(r.get("completion_tokens", 0) or 0)
        tt = int(r.get("total_tokens", pt + ct) or 0)
        cost = r.get("est_cost_usd", None)
        lat = r.get("latency_s", None)
        purpose = r.get("purpose", "delegation")
        purposes[purpose] = purposes.get(purpose, 0) + 1
        if r.get("aborted"):
            purposes["aborted"] = purposes.get("aborted", 0) + 1

        m = per_model.setdefault(model, {
            "backend": backend, "calls": 0, "prompt": 0, "completion": 0,
            "total": 0, "cost": 0.0, "cost_known": True, "time_s": 0.0, "timed": 0,
        })
        m["calls"] += 1
        m["prompt"] += pt
        m["completion"] += ct
        m["total"] += tt
        if cost is None:
            m["cost_known"] = False
            cost_known = False
        else:
            m["cost"] += cost
            tot["cost"] += cost
        if lat is not None:
            m["time_s"] += float(lat)
            m["timed"] += 1

        tot["prompt"] += pt
        tot["completion"] += ct
        tot["tokens"] += tt

        side = free if backend == "ollama" else paid
        side["calls"] += 1
        side["prompt"] += pt
        side["completion"] += ct
        side["tokens"] += tt
        if lat is not None:
            side["time_s"] += float(lat)
            side["timed"] += 1

    return {
        "per_model": per_model,
        "purposes": purposes,
        "total_tokens": tot["tokens"],
        "total_prompt": tot["prompt"],
        "total_completion": tot["completion"],
        "total_cost": round(tot["cost"], 4),
        "cost_known": cost_known,
        "free": free,
        "paid": paid,
        "calls": len(rows),
    }


def _savings(agg: dict) -> dict:
    """Price the free Ollama tokens as if they had gone to each paid tier."""
    f = agg["free"]
    would_cost = {
        tier: round(f["prompt"] / 1e6 * rin + f["completion"] / 1e6 * rout, 4)
        for tier, (rin, rout) in _RATES.items()
    }

    # Cost-vs-time: measured Ollama wall-time vs paid wall-time for the same
    # number of calls. Prefer measured paid latency from this log; fall back
    # to the routing-guide reference if no paid call has been timed.
    ollama_time = f["time_s"]
    timed_calls = f["timed"]
    p = agg["paid"]
    if p["timed"] > 0:
        paid_avg = p["time_s"] / p["timed"]
        paid_latency_src = f"measured avg of {p['timed']} paid call(s)"
    else:
        paid_avg = _PAID_REF_LATENCY_S
        paid_latency_src = f"reference ~{_PAID_REF_LATENCY_S:.0f}s/call (routing-guide; no paid calls timed yet)"
    est_paid_time = paid_avg * timed_calls
    extra_time = max(0.0, ollama_time - est_paid_time)
    saved_at_haiku = would_cost.get("haiku", 0.0)
    return {
        "free_tokens": f["tokens"],
        "would_cost": would_cost,
        "ollama_time_s": round(ollama_time, 1),
        "ollama_timed_calls": timed_calls,
        "est_paid_time_s": round(est_paid_time, 1),
        "paid_latency_src": paid_latency_src,
        "extra_time_s": round(extra_time, 1),
        "saved_usd_haiku": saved_at_haiku,
        "usd_saved_per_extra_min": (
            round(saved_at_haiku / (extra_time / 60), 4) if extra_time > 0 else None
        ),
    }


def _audit(rows: list[dict]) -> dict:
    """Find where Ollama enforcement broke down."""
    violations: list[dict] = []   # hard: a free-tier task billed to a paid model
    forced_paid: list[dict] = []  # soft: auto-routing fell back to paid (Ollama down)

    for r in rows:
        backend = r.get("backend")
        complexity = r.get("complexity")
        requested = r.get("requested")
        ollama_up = r.get("ollama_up")
        if backend != "openrouter":
            continue
        if complexity in _FREE_TIERS:
            violations.append({
                "ts": r.get("ts"), "model": r.get("model"),
                "complexity": complexity, "cost": r.get("est_cost_usd"),
                "reason": f"{complexity} task should route to Ollama (free) but hit paid {r.get('model')}",
            })
        elif requested == "auto" and ollama_up is False:
            forced_paid.append({
                "ts": r.get("ts"), "model": r.get("model"),
                "cost": r.get("est_cost_usd"),
                "reason": "Ollama was DOWN — auto-router could not use the free tier and fell back to paid",
            })

    return {"violations": violations, "forced_paid": forced_paid}


def _fmt_usd(x) -> str:
    if x is None:
        return "  (est n/a)"
    return f"${x:,.4f}"


def _render(agg: dict, audit: dict, sav: dict, path: Path, since_days) -> tuple[str, int]:
    L: list[str] = []
    win = f"last {since_days:g}d" if since_days else "all time"
    L.append("")
    L.append(f"  dom usage — {win}   ({path})")
    L.append("  " + "─" * 72)

    if agg["calls"] == 0:
        L.append("")
        L.append("  No delegated model calls logged yet.")
        L.append("  Generate some:  dom task <file> 'change' 'test'   (or ask_local in MCP)")
        L.append("")
        return "\n".join(L), 0

    # ── Tokens per model ──────────────────────────────────────────────
    L.append("")
    L.append("  TOKENS PER MODEL")
    L.append(f"  {'model':<27}{'backend':<11}{'calls':>6}{'tokens':>11}{'est cost':>11}{'time':>9}")
    L.append("  " + "-" * 72)
    for model, m in sorted(agg["per_model"].items(), key=lambda kv: kv[1]["total"], reverse=True):
        cost = _fmt_usd(m["cost"]) if m["cost_known"] else "  (est n/a)"
        t = f"{m['time_s']:,.1f}s" if m["timed"] else "—"
        L.append(f"  {model[:26]:<27}{m['backend']:<11}{m['calls']:>6}{m['total']:>11,}{cost:>11}{t:>9}")
    L.append("  " + "-" * 72)
    total_cost = _fmt_usd(agg["total_cost"]) if agg["cost_known"] else f"~{_fmt_usd(agg['total_cost'])}+"
    all_time = agg["free"]["time_s"] + agg["paid"]["time_s"]
    L.append(f"  {'TOTAL':<27}{'':<11}{agg['calls']:>6}{agg['total_tokens']:>11,}{total_cost:>11}{all_time:>8,.1f}s")
    L.append(f"       prompt {agg['total_prompt']:,} · completion {agg['total_completion']:,}"
             f" · purpose: " + " · ".join(f"{k} {v}" for k, v in sorted(agg["purposes"].items())))

    # ── Ollama savings ────────────────────────────────────────────────
    L.append("")
    L.append("  OLLAMA SAVINGS (same tokens priced at paid tiers)")
    L.append(f"  tokens run free locally:   {sav['free_tokens']:>10,}")
    for tier in ("haiku", "sonnet", "opus"):
        L.append(f"  would have cost @ {tier:<8} {_fmt_usd(sav['would_cost'][tier]):>10}")
    L.append(f"  actual paid spend:         {_fmt_usd(agg['total_cost']):>10}")

    # ── Cost vs time ─────────────────────────────────────────────────
    L.append("")
    L.append("  COST vs TIME")
    f, p = agg["free"], agg["paid"]
    favg = f"avg {f['time_s']/f['timed']:.1f}s/call" if f["timed"] else "no timed calls"
    pavg = f"avg {p['time_s']/p['timed']:.1f}s/call" if p["timed"] else "no timed calls"
    L.append(f"  time in Ollama (free):     {f['time_s']:>8,.1f}s over {f['calls']} calls ({favg})")
    L.append(f"  time in paid models:       {p['time_s']:>8,.1f}s over {p['calls']} calls ({pavg})")
    L.append(f"  same free calls at paid speed: ~{sav['est_paid_time_s']:,.1f}s  [{sav['paid_latency_src']}]")
    if sav["extra_time_s"] > 0 and sav["usd_saved_per_extra_min"] is not None:
        L.append(f"  tradeoff: waited {sav['extra_time_s']:,.1f}s extra to save {_fmt_usd(sav['saved_usd_haiku'])}"
                 f" (vs Haiku) ≈ {_fmt_usd(sav['usd_saved_per_extra_min'])}/extra-minute")
    else:
        L.append("  tradeoff: Ollama was as fast or faster than the paid reference — savings cost no time.")

    # ── Ollama enforcement ────────────────────────────────────────────
    calls = agg["calls"]
    free_pct = 100.0 * f["calls"] / calls
    L.append("")
    L.append("  OLLAMA ENFORCEMENT")
    L.append(f"  free (local Ollama):  {f['calls']:>4} / {calls}  ({free_pct:5.1f}%)")
    L.append(f"  paid (OpenRouter):    {p['calls']:>4} / {calls}  ({100 - free_pct:5.1f}%)")

    violations = audit["violations"]
    forced = audit["forced_paid"]
    exit_code = 0

    if violations:
        exit_code = 1
        L.append("")
        L.append(f"  ✗ {len(violations)} ENFORCEMENT VIOLATION(S) — free-tier work billed to paid models:")
        for v in violations[:20]:
            L.append(f"      • {v['ts']}  {v['reason']}  ({_fmt_usd(v['cost'])})")
        if len(violations) > 20:
            L.append(f"      … and {len(violations) - 20} more")
    if forced:
        L.append("")
        L.append(f"  ⚠ {len(forced)} call(s) forced to paid because Ollama was DOWN:")
        for fp in forced[:10]:
            L.append(f"      • {fp['ts']}  fell back to {fp['model']}  ({_fmt_usd(fp['cost'])})")
        if len(forced) > 10:
            L.append(f"      … and {len(forced) - 10} more")
        L.append("      Fix: keep `ollama serve` running so the free tier is available.")

    L.append("")
    if not violations and not forced:
        L.append("  ✓ PASS — no free-tier task hit a paid model; Ollama routing is holding.")
    elif not violations:
        L.append("  ✓ PASS (with warnings) — no misrouted free-tier work; see Ollama-down notes above.")
    else:
        L.append("  ✗ FAIL — see violations above. The router is paying for work Ollama should do free.")
    L.append("")
    return "\n".join(L), exit_code


def main() -> int:
    ap = argparse.ArgumentParser(description="dom token/cost/latency & Ollama-enforcement report")
    ap.add_argument("--log", help="path to usage.jsonl (default: autodetect .dom/usage.jsonl)")
    ap.add_argument("--bot", help="report on ANOTHER bot by registry name (e.g. `dom usage --bot smartballz`)")
    ap.add_argument("--since", type=float, metavar="DAYS", help="only count the last N days")
    ap.add_argument("--json", action="store_true", help="emit raw aggregates as JSON")
    ap.add_argument("--md", action="store_true", help="wrap the report in markdown (for saving as a report file)")
    args = ap.parse_args()

    path = _bot_log(args.bot) if args.bot else _find_log(args.log)
    rows = _load(path, args.since)
    agg = _aggregate(rows)
    audit = _audit(rows)
    sav = _savings(agg)

    if args.json:
        print(json.dumps({"log": str(path), "since_days": args.since,
                          "aggregate": agg, "savings": sav, "audit": audit},
                         indent=2, default=str))
        return 1 if audit["violations"] else 0

    report, code = _render(agg, audit, sav, path, args.since)
    if args.md:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"# dom usage report — {stamp}\n\n```text\n{report}\n```")
    else:
        print(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
