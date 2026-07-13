#!/usr/bin/env bash
#
# Freeze the ftt launcher into a single no-Python double-click app.
#
# Usage:   bash launcher/build.sh
# Make it executable (optional):  chmod +x launcher/build.sh && ./launcher/build.sh
#
# PyInstaller does NOT cross-compile — run this on each target OS (or in a
# per-OS CI runner) to produce that platform's artifact in ./dist/.

set -euo pipefail

# Resolve repo root as the parent of this script's directory so the command
# works regardless of the current working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENTRY="launcher/ftt_launcher.py"

cd "${REPO_ROOT}"

if ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller is not installed."
  echo
  echo "Install it, then re-run this script:"
  echo "    pip install pyinstaller"
  echo "    bash launcher/build.sh"
  exit 1
fi

echo "Freezing ${ENTRY} with PyInstaller (--onefile --windowed)..."
python3 -m PyInstaller --onefile --windowed --name ftt_launcher "${ENTRY}"

echo
echo "Done. Artifact(s) in: ${REPO_ROOT}/dist/"
echo "  Linux:   dist/ftt_launcher"
echo "  macOS:   dist/ftt_launcher (+ .app bundle when built on macOS)"
echo "  Windows: dist/ftt_launcher.exe (when built on Windows)"
