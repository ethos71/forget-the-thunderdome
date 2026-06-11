#!/bin/bash
# Refresh the job-search dashboard from live Gmail + the local tracker DB.
#
# Usage:
#   ./dashboard/refresh-dashboard.sh
#
# 1. Syncs recent recruiter emails into data/job_tracker.db
# 2. Prints the CLI dashboard from the local DB
#
# TODO(ftt): the original private project also rendered an HTML dashboard
# (index.html) from the DB plus an apply_ready.yaml curation file. Neither the
# HTML template nor the renderer script ship in this repo yet. To add one,
# generate HTML from the queries in src/job_automation.py (ApplicationTracker
# .get_dashboard) and write it to dashboard/index.html.

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
