#!/bin/bash
# First-time VPS bootstrap — run once from your LOCAL machine.
#
# Usage:
#   bash scripts/bootstrap_vps.sh root@your-server.com [your-domain.com]
#
# What it does:
#   1. Uploads the local SQLite DB to the VPS (so no cold re-download needed)
#   2. SSHs in and runs setup.sh (venv, nginx, systemd service)
#   3. Prints the GitHub Actions secrets to add

set -euo pipefail

SSH_TARGET="${1:-}"
DOMAIN="${2:-}"

if [ -z "$SSH_TARGET" ]; then
  echo "Usage: bash scripts/bootstrap_vps.sh root@your-server.com [your-domain.com]"
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_DB="$REPO_ROOT/dashboard.db"

if [ ! -f "$LOCAL_DB" ]; then
  echo "ERROR: $LOCAL_DB not found."
  echo "Run first: python3 scripts/migrate_to_db.py"
  exit 1
fi

DB_SIZE=$(du -sh "$LOCAL_DB" | cut -f1)
echo "==> Local DB: $LOCAL_DB ($DB_SIZE)"

# ── Step 1: Clone repo on VPS ──────────────────────────────────────
REPO_URL=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || echo "")
if [ -z "$REPO_URL" ]; then
  echo "ERROR: could not determine remote URL (is this a git repo with an 'origin' remote?)"
  exit 1
fi

echo "==> Cloning $REPO_URL on VPS"
ssh "$SSH_TARGET" bash << REMOTE
set -e
if [ -d /opt/etf-dashboard/.git ]; then
  echo "  Repo already exists — pulling latest"
  cd /opt/etf-dashboard && git pull origin main
else
  git clone "$REPO_URL" /opt/etf-dashboard
fi
mkdir -p /opt/etf-dashboard/data
REMOTE

# ── Step 2: Upload the database ────────────────────────────────────
echo "==> Uploading dashboard.db ($DB_SIZE) → VPS /opt/etf-dashboard/data/"
echo "    (this may take a moment depending on your connection)"
scp "$LOCAL_DB" "$SSH_TARGET:/opt/etf-dashboard/data/dashboard.db"
echo "    ✓ Uploaded"

# ── Step 3: Run setup.sh on VPS ────────────────────────────────────
echo "==> Running setup.sh on VPS"
ssh -t "$SSH_TARGET" bash << REMOTE
set -e
cd /opt/etf-dashboard
bash dashboard/deploy/setup.sh "$DOMAIN"
REMOTE

echo ""
echo "✓ Bootstrap complete!"
echo ""
echo "  Your dashboard should now be live at:"
if [ -n "$DOMAIN" ]; then
  echo "    https://$DOMAIN  (or http://$DOMAIN until HTTPS is configured)"
else
  echo "    http://$(ssh "$SSH_TARGET" 'curl -s ifconfig.me 2>/dev/null || echo <server-ip>')"
fi
echo ""
echo "  From now on, updates are automatic:"
echo "    git push origin main  →  GitHub Actions deploys in ~30s"
