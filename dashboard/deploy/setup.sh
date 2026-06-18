#!/bin/bash
# First-time VPS setup — run once as root on Ubuntu 22.04 / Debian 12.
# Assumes Caddy is already installed on the VPS.
#
# Usage: bash dashboard/deploy/setup.sh [domain.example.com]
#
# Sets up:
#   - Python venv + dependencies
#   - SQLite DB (migrated or verified)
#   - systemd service (uvicorn on 127.0.0.1:8765)
#   - Caddy reverse proxy (automatic HTTPS)
#   - Deploy user with SSH key for GitHub Actions CD

set -euo pipefail

DOMAIN="${1:-}"
DEPLOY_DIR="/home/ubuntu/etf-ppm-stocks"
APP_USER="ubuntu"
VENV="$DEPLOY_DIR/venv"
SERVICE="etf-dashboard"

# ── 1. System packages ─────────────────────────────────────────────
echo "==> Installing system packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip rsync

# ── 2. Sudoers for service restart ────────────────────────────────
SUDOERS_LINE="$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart $SERVICE"
grep -qF "$SUDOERS_LINE" /etc/sudoers 2>/dev/null || echo "$SUDOERS_LINE" >> /etc/sudoers

# ── 3. Python venv ─────────────────────────────────────────────────
echo "==> Creating Python virtualenv"
sudo -u "$APP_USER" python3 -m venv "$VENV"
sudo -u "$APP_USER" "$VENV/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$VENV/bin/pip" install -q -r "$DEPLOY_DIR/dashboard/backend/requirements.txt"

# ── 4. Data directory + config seed ────────────────────────────────
echo "==> Setting up data directory"
DATA_DIR="$DEPLOY_DIR/data"
mkdir -p "$DATA_DIR"
for f in config.json screening_config.json; do
  [ -f "$DATA_DIR/$f" ] || cp "$DEPLOY_DIR/dashboard/backend/$f" "$DATA_DIR/$f"
done
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"

# ── 6. DB (skip migration if DB already uploaded) ─────────────────
if [ -f "$DATA_DIR/dashboard.db" ]; then
  echo "==> Found existing database — skipping migration"
  sudo -u "$APP_USER" DATA_DIR="$DATA_DIR" \
    "$VENV/bin/python3" "$DEPLOY_DIR/scripts/migrate_to_db.py" \
    --verify --db "$DATA_DIR/dashboard.db"
else
  echo "==> No database found — running migration from source files"
  sudo -u "$APP_USER" DATA_DIR="$DATA_DIR" \
    "$VENV/bin/python3" "$DEPLOY_DIR/scripts/migrate_to_db.py" \
    --db "$DATA_DIR/dashboard.db" \
    || echo "  (migration failed — engine will re-download from yfinance on first run)"
fi

# ── 7. Initial engine run ──────────────────────────────────────────
echo "==> Running initial engine calculation (~30 s)"
sudo -u "$APP_USER" DATA_DIR="$DATA_DIR" \
  "$VENV/bin/python3" "$DEPLOY_DIR/dashboard/backend/engine.py" \
  || echo "  (engine run failed — will retry on first scheduler tick)"

# ── 8. systemd service ─────────────────────────────────────────────
echo "==> Installing systemd service"
cat > /etc/systemd/system/etf-dashboard.service << EOF
[Unit]
Description=ETF Rotation Dashboard (uvicorn)
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$DEPLOY_DIR/dashboard/backend
Environment=DATA_DIR=$DATA_DIR
ExecStart=$VENV/bin/uvicorn main:app --host 127.0.0.1 --port 8765 --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
# Uncomment to protect write endpoints:
# Environment=DASHBOARD_SECRET=change-me

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"
systemctl is-active "$SERVICE" && echo "  ✓ service running" \
  || (echo "  ✗ service failed"; journalctl -u "$SERVICE" -n 20; exit 1)

# ── 9. Caddy ───────────────────────────────────────────────────────
echo "==> Configuring Caddy"
CADDY_SITE="/etc/caddy/sites/$SERVICE"
mkdir -p /etc/caddy/sites

if [ -n "$DOMAIN" ]; then
  cat > "$CADDY_SITE" << EOF
$DOMAIN {
    reverse_proxy localhost:8765
}
EOF
  echo "  Site: $DOMAIN → localhost:8765 (Caddy handles HTTPS automatically)"
else
  cat > "$CADDY_SITE" << EOF
:80 {
    reverse_proxy localhost:8765
}
EOF
  echo "  No domain provided — serving on port 80 (HTTP only)"
fi

# Include sites dir in main Caddyfile if not already there
CADDYFILE="/etc/caddy/Caddyfile"
if ! grep -q "sites/\*" "$CADDYFILE" 2>/dev/null; then
  echo "import sites/*" >> "$CADDYFILE"
fi
caddy validate --config "$CADDYFILE" && systemctl reload caddy \
  && echo "  ✓ Caddy reloaded" \
  || echo "  ✗ Caddy reload failed (check: journalctl -u caddy)"

# ── 10. SSH key for GitHub Actions ────────────────────────────────
echo ""
echo "==> Generating SSH deploy key for GitHub Actions"
SSH_DIR="/home/$APP_USER/.ssh"
mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"
KEY_FILE="$SSH_DIR/github_actions_ed25519"

if [ ! -f "$KEY_FILE" ]; then
  ssh-keygen -t ed25519 -C "github-actions-deploy" -N "" -f "$KEY_FILE"
  cat "$KEY_FILE.pub" >> "$SSH_DIR/authorized_keys"
  chmod 600 "$SSH_DIR/authorized_keys"
  chown -R "$APP_USER:$APP_USER" "$SSH_DIR"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Add these 3 secrets in GitHub repo settings:  "
echo " Settings → Secrets → Actions → New secret     "
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  VPS_HOST   $(curl -s ifconfig.me 2>/dev/null || echo '<server-ip>')"
echo "  VPS_USER   $APP_USER"
echo "  VPS_SSH_KEY  (paste the key below)"
echo ""
cat "$KEY_FILE"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✓ Setup complete!"
[ -n "$DOMAIN" ] && echo "  Dashboard: https://$DOMAIN" \
                 || echo "  Dashboard: http://$(curl -s ifconfig.me 2>/dev/null)"
echo ""
echo "  Logs:    journalctl -u $SERVICE -f"
echo "  Restart: systemctl restart $SERVICE"
echo "  PPM update: curl -X POST https://${DOMAIN:-localhost}/api/import-ppm -F 'file=@file.xlsx'"
