#!/bin/bash
# Refresh the job-search dashboard from live Gmail + the local tracker DB.
#
# Usage:
#   ./dashboard/refresh-dashboard.sh
#
# 1. Syncs recent recruiter emails into data/job_tracker.db
# 2. Prints the CLI dashboard from the local DB
# 3. Renders a self-contained HTML dashboard to dashboard/index.html

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ -f venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

# 1. Pull recent recruiter email activity into the DB (skips gracefully if
#    Gmail credentials are not configured yet).
python3 mcp-servers/gmail-server/gmail_tracker.py --sync --days 14 \
  || echo "⚠️  Gmail sync skipped (see docs/providers/gmail-setup.md)"

# 2. Re-render the dashboard from the local DB.
python3 src/job_cli.py dashboard

# 3. Also render the self-contained HTML dashboard to dashboard/index.html.
python3 src/job_cli.py dashboard --html
