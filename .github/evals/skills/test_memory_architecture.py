#!/usr/bin/env python3
"""Memory-architecture eval — enforces docs/robots/ shape.

What this pins
--------------
Every project that consumes @dom must keep its AI memory under
`docs/robots/`. The structure is load-bearing because it's how
fresh AI sessions get oriented:

  docs/robots/
  ├── README.md       — index + reading order
  └── MEMORY.md       — three-tier session memory (🔴 / 🟡 / 🟢)

Rules under test
~~~~~~~~~~~~~~~~
1. `docs/robots/` exists.
2. `docs/robots/README.md` exists and references MEMORY.md.
3. `docs/robots/MEMORY.md` exists and contains all three tier markers
   (🔴 short-term, 🟡 mid-term, 🟢 long-term).
4. `MEMORY.md` "Last Updated:" line is within the last 30 days
   (warning, not failure — staleness is real but not always a regression).

Skips if `docs/robots/` is missing AND the project is new — the
existence of `.github/skills/` signals an established project.
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROBOTS = PROJECT_ROOT / "docs" / "robots"


def main() -> int:
    skills_present = (PROJECT_ROOT / ".github" / "skills").is_dir()

    if not ROBOTS.is_dir():
        if not skills_present:
            print(f"⚠️  Skipping — fresh project (no .github/skills/, no docs/robots/)")
            return 0
        print(f"✗ docs/robots/ missing (project has skills — memory required)")
        print(f"  Bootstrap: copy templates/docs/robots/ from the @dom repo")
        return 1

    failures: list[str] = []
    readme = ROBOTS / "README.md"
    memory = ROBOTS / "MEMORY.md"

    print("=" * 60)
    print("memory-architecture eval")
    print("=" * 60)

    if not readme.exists():
        failures.append("docs/robots/README.md missing")
        print(f"  ✗ {failures[-1]}")
    elif "MEMORY.md" not in readme.read_text():
        failures.append("docs/robots/README.md does not reference MEMORY.md")
        print(f"  ✗ {failures[-1]}")
    else:
        print("  ✓ README.md present + references MEMORY.md")

    if not memory.exists():
        failures.append("docs/robots/MEMORY.md missing")
        print(f"  ✗ {failures[-1]}")
        return 1

    text = memory.read_text()
    for marker, name in (("🔴", "short-term"), ("🟡", "mid-term"), ("🟢", "long-term")):
        if marker not in text:
            failures.append(f"MEMORY.md missing {marker} ({name}) tier")
            print(f"  ✗ {failures[-1]}")
        else:
            print(f"  ✓ MEMORY.md has {marker} {name} tier")

    # Staleness: warn, don't fail.
    m = re.search(r"Last Updated:\s*\**\s*(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            last = date.fromisoformat(m.group(1))
            age_days = (date.today() - last).days
            if age_days > 30:
                print(f"  ⚠ MEMORY.md last updated {age_days} days ago — refresh soon")
            else:
                print(f"  ✓ MEMORY.md last updated {age_days} days ago")
        except ValueError:
            print(f"  ⚠ MEMORY.md 'Last Updated' is not ISO date")
    else:
        print(f"  ⚠ MEMORY.md missing 'Last Updated:' line")

    print("=" * 60)
    if failures:
        print(f"FAILED: {len(failures)} memory-architecture issues")
        return 1
    print("PASSED — docs/robots/ memory architecture holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
