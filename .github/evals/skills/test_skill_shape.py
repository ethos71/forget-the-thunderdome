#!/usr/bin/env python3
"""Skill-shape eval — every `.github/skills/<name>/` must hold a
consistent four-part shape (SKILL.md + README.md + references/ + scripts/).

Without this rule, the skill router has nothing to discover and skills
rot into SKILL.md-only stubs. The `dom-eval-enforcer` agent uses this
eval to gate new skill additions.

Exempt list: meta-skills whose primary deliverable is something
other than scripts + references — pure routers like `help`, and
template-shipping skills like `bootstrap` whose deliverable lives
under `templates/`. SKILL.md + README.md are still required. Keep
this list tiny — every exemption is technical debt.
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = PROJECT_ROOT / ".github" / "skills"

EXEMPT_FROM_DIRS = {"help", "bootstrap"}


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


def _score_skill(skill_dir: Path) -> list[str]:
    issues: list[str] = []
    name = skill_dir.name

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        issues.append("missing SKILL.md")
    else:
        fm = _parse_frontmatter(skill_md.read_text())
        if fm.get("name") != name:
            issues.append(
                f"SKILL.md frontmatter name={fm.get('name')!r} ≠ folder {name!r}"
            )
        if not fm.get("description"):
            issues.append("SKILL.md frontmatter description empty")

    if not (skill_dir / "README.md").exists():
        issues.append("missing README.md")

    if name not in EXEMPT_FROM_DIRS:
        refs = skill_dir / "references"
        if not refs.is_dir() or not any(refs.glob("*.md")):
            issues.append("references/ missing or empty (need ≥1 .md)")
        scripts = skill_dir / "scripts"
        if not scripts.is_dir() or not any(scripts.glob("*.sh")):
            issues.append("scripts/ missing or empty (need ≥1 .sh)")

    return issues


def main() -> int:
    if not SKILLS_DIR.is_dir():
        print(f"⚠️  Skipping — {SKILLS_DIR} not found")
        return 0

    skills = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
    if not skills:
        print(f"⚠️  Skipping — no skills under {SKILLS_DIR}")
        return 0

    print("=" * 60)
    print(f"skill-shape eval — {len(skills)} skills")
    print("=" * 60)

    failed = 0
    for skill in skills:
        issues = _score_skill(skill)
        if issues:
            failed += 1
            print(f"  ✗ {skill.name}")
            for i in issues:
                print(f"      → {i}")
        else:
            print(f"  ✓ {skill.name}")

    print("=" * 60)
    if failed:
        print(f"FAILED: {failed} / {len(skills)} skills missing required shape")
        print("Reference: docs/eval-policy.md → 'Skill structure'.")
        return 1
    print(f"PASSED: all {len(skills)} skills hold the required shape")
    return 0


if __name__ == "__main__":
    sys.exit(main())
