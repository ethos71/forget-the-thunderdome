#!/usr/bin/env python3
"""Role-shape eval — every `.github/roles/<name>.md` must hold a
consistent shape: frontmatter (name == filename, non-empty
description) plus three required sections (Scope, What it owns,
What it talks to).

Roles are ownership boundaries one level above skills. Without this
rule, a `roles/` directory rots into single-sentence stubs that don't
say who actually owns what. The `dom-eval-enforcer` agent uses this
eval to gate new role additions.

`README.md` inside `roles/` is exempt — it indexes the roles, it is
not itself a role.
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROLES_DIR = PROJECT_ROOT / ".github" / "roles"

EXEMPT_FILES = {"README.md"}

REQUIRED_SECTIONS = (
    "## Scope",
    "## What it owns",
    "## What it talks to",
)


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    body = text[3:end].strip()
    out: dict[str, str] = {}
    key: str | None = None
    buf: list[str] = []
    for raw in body.splitlines():
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)$", raw)
        if m:
            if key is not None:
                out[key] = " ".join(buf).strip()
            key = m.group(1)
            val = m.group(2).strip()
            buf = [val] if val and val not in (">-", ">") else []
        else:
            if key:
                buf.append(raw.strip())
    if key is not None:
        out[key] = " ".join(buf).strip()
    return out


def _score_role(role_md: Path) -> list[str]:
    issues: list[str] = []
    expected_name = role_md.stem
    text = role_md.read_text()

    fm = _parse_frontmatter(text)
    if not fm:
        issues.append("missing frontmatter (--- ... ---)")
    else:
        if fm.get("name") != expected_name:
            issues.append(
                f"frontmatter name={fm.get('name')!r} ≠ filename {expected_name!r}"
            )
        if not fm.get("description"):
            issues.append("frontmatter description empty")

    for section in REQUIRED_SECTIONS:
        if section not in text:
            issues.append(f"missing section '{section}'")

    return issues


# Model pins must be TIER ALIASES the router owns — never dated ids or
# marketing names ('claude-haiku-4-5-20251001', 'Claude Sonnet 4.5'). Dated
# pins rot silently and bypass the cheapest-capable-wins waterfall; the
# alias→id mapping lives in ONE place (agent_tools._OPENROUTER_ALIASES) and
# is currency-checked by check-rates.py.
ALLOWED_MODEL_PINS = {"ollama", "haiku", "sonnet", "opus", "auto"}
AGENTS_DIR = PROJECT_ROOT / ".github" / "agents"


def _check_model_pins() -> list[tuple[str, str]]:
    """Return (file, issue) for every agent/role whose model: pin is not a tier alias."""
    bad: list[tuple[str, str]] = []
    for d in (ROLES_DIR, AGENTS_DIR):
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            fm = _parse_frontmatter(md.read_text())
            pin = fm.get("model", "").strip().strip("'\"")
            if pin and pin.lower() not in ALLOWED_MODEL_PINS:
                bad.append((
                    f"{d.name}/{md.name}",
                    f"model: {pin!r} is not a tier alias — use one of "
                    f"{sorted(ALLOWED_MODEL_PINS)} (aliases resolve in agent_tools.py)",
                ))
    return bad


def main() -> int:
    if not ROLES_DIR.is_dir():
        print(f"⚠️  Skipping — {ROLES_DIR} not found")
        return 0

    roles = sorted(
        p for p in ROLES_DIR.glob("*.md") if p.name not in EXEMPT_FILES
    )
    if not roles:
        print(f"⚠️  Skipping — no role files under {ROLES_DIR}")
        return 0

    print("=" * 60)
    print(f"role-shape eval — {len(roles)} roles")
    print("=" * 60)

    failed = 0
    for role in roles:
        issues = _score_role(role)
        if issues:
            failed += 1
            print(f"  ✗ {role.stem}")
            for i in issues:
                print(f"      → {i}")
        else:
            print(f"  ✓ {role.stem}")

    # Model-pin policy applies to roles AND agents.
    bad_pins = _check_model_pins()
    if bad_pins:
        print("-" * 60)
        for path, issue in bad_pins:
            failed += 1
            print(f"  ✗ {path}")
            print(f"      → {issue}")

    print("=" * 60)
    if failed:
        print(f"FAILED: {failed} shape/model-pin issue(s)")
        print("Reference: .github/roles/README.md → 'File shape'; docs/routing-guide.md → tiers.")
        return 1
    print(f"PASSED: all {len(roles)} roles hold the required shape; model pins are tier aliases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
