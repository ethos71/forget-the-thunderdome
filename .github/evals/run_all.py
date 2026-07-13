#!/usr/bin/env python3
"""Run every eval in this project. Exit 0 if all pass/skip, 1 if any fails.

Register suites below as you add them.

Usage:
    python .github/evals/run_all.py
    python .github/evals/run_all.py --only voice
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]

# (bucket, path-relative-to-ROOT, timeout-seconds)
SUITES: list[tuple[str, str, int]] = [
    # Example entries — uncomment and adapt as you add evals:
    # ("ai",     "ai/test_hallucinations.py",           300),
    # ("tools",  "tools/test_my_tool.py",               120),
    # ("skills", "skills/test_my_skill_contract.py",     60),
    # ("voice",  "voice/test_my_voice.py",              120),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        choices=sorted({b for b, _, _ in SUITES}) or None,
        help="Run a single bucket.",
    )
    args = parser.parse_args()

    suites = [s for s in SUITES if not args.only or s[0] == args.only]
    if not suites:
        print("⚠️  No evals registered. Add entries to SUITES in this file.")
        return 0

    print("=" * 60)
    print(f"EVALS — {len(suites)} suite(s)")
    print("=" * 60)

    failed = 0
    results: list[tuple[str, str, int]] = []
    for bucket, rel, timeout in suites:
        path = ROOT / rel
        if not path.exists():
            print(f"\n⚠️  Skipping {rel}: not found")
            continue
        print(f"\n▶ [{bucket}] {rel}")
        print("─" * 60)
        try:
            rc = subprocess.run(
                [sys.executable, str(path)],
                cwd=str(PROJECT_ROOT),
                timeout=timeout,
            ).returncode
        except subprocess.TimeoutExpired:
            print(f"  ⚠️  TIMEOUT after {timeout}s")
            rc = 1
        results.append((bucket, rel, rc))
        if rc:
            failed += 1

    print(f"\n{'=' * 60}\nSUMMARY")
    for bucket, rel, rc in results:
        mark = "✅ PASS" if rc == 0 else "❌ FAIL"
        print(f"  {mark}  [{bucket:6s}] {rel}")
    print(f"\n  {failed} failed\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
