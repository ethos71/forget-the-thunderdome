#!/usr/bin/env python3
"""Toolkit smoke eval — the toolkit must actually FUNCTION, not just hold shape.

Two checks, both against real content (never exit-code-only):

1. **delegate import contract.** Parse `.github/commands/dom-tools.sh` for the
   exact `sys.path.insert(...)` lines and `from <pkg> import delegate_task`
   that `dom task` executes, then run precisely that in a subprocess and assert
   the resolved `delegate_task` is a callable defined INSIDE this repo.
   This is the eval that would have caught the 2026-07-10 break where the
   shipped template imported `github_mcp.tools` — a package no consumer ever
   had — leaving `dom task` silently dead on every standard install. Parsing
   the repo's own dom-tools.sh (instead of assuming the default) means custom
   layouts (e.g. smartballz's `src.mcp.tools`) pass on their own terms.
   Falls back to the legacy `sbz-tools.sh` for consumers that have not yet
   re-installed across the sbz→dom rename.

2. **Universal-eval freshness.** Every eval listed in `MANIFEST.sha256`
   (shipped by install.sh, regenerated in dom via `gen_manifest.py`) must
   exist and hash-match. Catches silent drift: consumers found 2026-07-10
   with 0/3 or 2/3 evals present, others carrying stale versions.
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOM_TOOLS = PROJECT_ROOT / ".github" / "commands" / "dom-tools.sh"
SBZ_LEGACY = PROJECT_ROOT / ".github" / "commands" / "sbz-tools.sh"
MANIFEST = Path(__file__).resolve().parent / "MANIFEST.sha256"


def _tools_file() -> Path | None:
    """The file holding the `dom task` implementation + its import line.

    Prefer dom-tools.sh; fall back to a legacy (pre-rename) sbz-tools.sh that
    still carries the real implementation. A post-rename sbz-tools.sh is a thin
    shim with no import line, so dom-tools.sh always wins when both exist.
    """
    if DOM_TOOLS.exists():
        return DOM_TOOLS
    if SBZ_LEGACY.exists():
        return SBZ_LEGACY
    return None


def check_delegate_import() -> list[str]:
    """Execute the exact import contract dom-tools.sh uses. Return issues."""
    tools = _tools_file()
    if tools is None:
        return ["missing .github/commands/dom-tools.sh — toolkit not installed (rerun install.sh)"]

    # In dom itself dom-tools.sh is the unpatched template; consumers have the
    # placeholder substituted by install.sh. Substitute for both cases.
    text = tools.read_text(encoding="utf-8").replace("DOM_PROJECT_DIR", str(PROJECT_ROOT))

    inserts = re.findall(r"sys\.path\.insert\(0,\s*'([^']+)'\)", text)
    m = re.search(r"^from ([A-Za-z_][\w.]*) import delegate_task\s*$", text, re.MULTILINE)
    if not m:
        return [f"{tools.name} has no `from <pkg> import delegate_task` line — `dom task` cannot work"]
    import_pkg = m.group(1)

    probe_lines = ["import sys"]
    probe_lines += [f"sys.path.insert(0, {p!r})" for p in inserts]
    probe_lines += [
        f"from {import_pkg} import delegate_task",
        "import inspect",
        "assert callable(delegate_task), 'delegate_task is not callable'",
        "src = inspect.getsourcefile(delegate_task)",
        "params = list(inspect.signature(delegate_task).parameters)",
        "assert 'files' in params and 'change' in params, f'unexpected signature: {params}'",
        "print('RESOLVED::' + src)",
    ]
    probe = "\n".join(probe_lines)

    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip().splitlines()
        tail = err[-1] if err else "(no output)"
        return [f"delegate import contract FAILS: `from {import_pkg} import delegate_task` → {tail}"]

    resolved = next(
        (ln[len("RESOLVED::"):] for ln in result.stdout.splitlines() if ln.startswith("RESOLVED::")),
        "",
    )
    try:
        inside = Path(resolved).resolve().is_relative_to(PROJECT_ROOT)
    except (AttributeError, ValueError, OSError):
        inside = str(PROJECT_ROOT) in resolved
    if not inside:
        return [f"delegate_task resolved OUTSIDE this repo: {resolved} (shadowed by site-packages?)"]
    return []


def check_manifest() -> list[str]:
    """Every eval in MANIFEST.sha256 exists and hash-matches. Return issues."""
    if not MANIFEST.exists():
        return ["MANIFEST.sha256 missing — partial/hand-copied install (rerun install.sh)"]
    issues: list[str] = []
    entries = 0
    for raw in MANIFEST.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        try:
            want_hash, name = raw.split(None, 1)
        except ValueError:
            issues.append(f"malformed manifest line: {raw!r}")
            continue
        entries += 1
        path = MANIFEST.parent / name.strip()
        if not path.exists():
            issues.append(f"universal eval MISSING: {name} (rerun install.sh)")
            continue
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want_hash:
            issues.append(f"universal eval STALE: {name} differs from shipped version (rerun install.sh)")
    if entries == 0:
        issues.append("MANIFEST.sha256 lists no evals — regenerate with gen_manifest.py")
    return issues


def main() -> int:
    print("=" * 60)
    print("toolkit-smoke eval — delegate import contract + eval freshness")
    print("=" * 60)

    failed = 0
    for label, issues in (("delegate import contract", check_delegate_import()),
                          ("universal-eval freshness", check_manifest())):
        if issues:
            failed += 1
            print(f"  ✗ {label}")
            for i in issues:
                print(f"      → {i}")
        else:
            print(f"  ✓ {label}")

    print("=" * 60)
    if failed:
        print(f"FAILED: {failed} toolkit-smoke check(s) — the toolkit does not function here")
        return 1
    print("PASSED: delegate import resolves in-repo and universal evals are current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
