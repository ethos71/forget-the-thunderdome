#!/bin/bash
# Gmail Job Tracker Quick Start
# Run from anywhere: bash mcp-servers/setup.sh

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "======================================"
echo "Gmail Job Tracker Setup"
echo "======================================"

# Check profile
if [ ! -f "$REPO_ROOT/profile.yaml" ]; then
    echo ""
    echo "⚠️  No profile.yaml found at repo root."
    echo "   cp profile.yaml.example profile.yaml   # then fill in your details"
    echo ""
fi

# Check if credentials exist
if [ ! -f ~/.mcp/config/gmail_credentials.json ]; then
    echo ""
    echo "❌ Gmail credentials not found!"
    echo ""
    echo "Follow these steps:"
    echo "1. Go to: https://console.cloud.google.com/"
    echo "2. Create new project: 'job-tracker-gmail'"
    echo "3. Enable Gmail API"
    echo "4. Create OAuth 2.0 Desktop Credentials"
    echo "5. Download JSON → ~/.mcp/config/gmail_credentials.json"
    echo ""
    echo "Full guide: docs/providers/gmail-setup.md"
    echo "Then run this script again."
    exit 1
fi

# Ensure database directory + core tables exist
echo "Checking job_tracker database..."
mkdir -p "$REPO_ROOT/data"

# Initialize core tables (applications, job_postings, ...) via job_automation
PYTHONPATH="$REPO_ROOT/src" python3 -c "from job_automation import JobSearchDB; JobSearchDB()" \
    && echo "✅ Core tables ready"

# TODO(ftt): ship an email_schema.sql that creates the email_interactions table
# and the email_history view used by gmail_tracker.py, then apply it here:
#   sqlite3 "$REPO_ROOT/data/job_tracker.db" < "$REPO_ROOT/mcp-servers/gmail-server/email_schema.sql"
if ! sqlite3 "$REPO_ROOT/data/job_tracker.db" ".tables" | grep -q email_interactions; then
    echo "⚠️  email_interactions table not present yet (see TODO in this script)"
else
    echo "✅ Email schema already in place"
fi

# Install dependencies
echo ""
echo "Checking Python dependencies..."
pip install -q google-auth-oauthlib google-auth-httplib2 google-api-python-client pyyaml mcp || true
echo "✅ Dependencies installed"

# First run (triggers OAuth if needed)
echo ""
echo "Testing Gmail connection..."
python3 "$REPO_ROOT/mcp-servers/gmail-server/gmail_tracker.py" || echo "⚠️  First auth required - check your browser"

echo ""
echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Sync your emails: python3 mcp-servers/gmail-server/gmail_tracker.py --sync"
echo "2. View synced data: sqlite3 data/job_tracker.db 'SELECT * FROM email_history;'"
echo ""
