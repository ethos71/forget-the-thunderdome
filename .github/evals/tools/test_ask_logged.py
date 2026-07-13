#!/usr/bin/env python3
"""Metered-ask eval — the shell `ask` command must log every model call.

Rule pinned: free Q&A must be metered (dom TODO, Phase 1). The shell
`ask` helper was the last unmetered model surface in the toolkit; every
real call it makes must land in the usage log as a purpose=="adhoc" row
with real token counts, or `dom usage` under-reports local spend and
the Ollama cost audit is blind to ad-hoc Q&A.

Oracle: the JSONL usage-log file written during the run — assertions
compare against its data content (purpose + total_tokens), never exit
codes alone. Skip-safe per eval-policy: exits 0 with a ⚠️ message when
local Ollama is not reachable at http://localhost:11434 or the `openai`
package is missing. Fix site on failure: `.github/commands/ask`.
"""

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ASK = PROJECT_ROOT / ".github" / "commands" / "ask"
OLLAMA_TAGS = "http://localhost:11434/api/tags"
QUESTION = "Reply with the single word OK"


def _ollama_up() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_TAGS, timeout=3):
            return True
    except Exception:
        return False


def main() -> int:
    try:
        import openai  # noqa: F401
    except ImportError:
        print("⚠️  Skipping — `openai` package not installed (metered path needs it)")
        return 0
    if not _ollama_up():
        print(f"⚠️  Skipping — local Ollama not reachable at {OLLAMA_TAGS}; start `ollama serve`")
        return 0
    if not ASK.is_file():
        print(f"FAIL: ask command not found at {ASK}")
        return 1

    print("=" * 64)
    print("metered-ask eval — shell `ask` must log a purpose=adhoc row")
    print("=" * 64)

    with tempfile.NamedTemporaryFile(mode="r", suffix=".jsonl", prefix="dom-ask-eval-") as log:
        env = dict(os.environ, DOM_USAGE_LOG=log.name)
        proc = subprocess.run(
            ["bash", str(ASK), QUESTION],
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            stdin=subprocess.DEVNULL,
            cwd=str(PROJECT_ROOT),
        )
        log_text = Path(log.name).read_text(encoding="utf-8")

    if proc.returncode != 0:
        print(f"FAIL: `ask '{QUESTION}'` exited {proc.returncode}")
        print(f"  stderr: {proc.stderr.strip()[:300]}")
        print("  Fix: .github/commands/ask (metered path must answer via ask_local)")
        return 1

    rows = []
    for line in log_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"FAIL: non-JSON line in usage log: {line[:120]!r}")
            print("  Fix: .github/commands/ask / agent_tools._log_usage — log must stay JSONL")
            return 1

    adhoc = [r for r in rows if r.get("purpose") == "adhoc" and r.get("total_tokens", 0) > 0]
    if not adhoc:
        print("FAIL: rule 'free Q&A must be metered' violated —")
        print(f"  the run logged {len(rows)} row(s), none with purpose=='adhoc' and total_tokens>0.")
        print(f"  Log content: {log_text.strip()[:300] or '(empty)'}")
        print("  Fix: .github/commands/ask must route through agent_tools.ask_local()")
        print("  (which appends the adhoc row), not raw `ollama run`.")
        return 1

    r = adhoc[0]
    print(f"PASS: ask call metered — model={r.get('model')} "
          f"total_tokens={r.get('total_tokens')} latency_s={r.get('latency_s')}")
    print(f"  answer preview: {proc.stdout.strip()[:80]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
