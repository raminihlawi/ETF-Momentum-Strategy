#!/bin/bash
# First-time VPS setup — run once as root on Ubuntu 22.04 / Debian 12.
# Usage: bash dashboard/deploy/setup.sh [domain.example.com]
#
# Sets up:
#   - Python venv + dependencies
#   - SQLite DB migration (existing pickle + CSV data)
#   - systemd service (uvicorn)
#   - nginx reverse proxy
#   - Let's Encrypt HTTPS (optional)
#   - Deploys user (etf) with SSH key for GitHub Actions CD

set -euo pipefail

DOMAIN="${1:-}"
DEPLOY_DIR="/opt/etf-dashboard"
APP_USER="etf"
VENV="$DEPLOY_DIR/venv"
SERVICE="etf-dashboard"
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

# ── 1. System packages ─────────────────────────────────────────────
echo "==> Installing system packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx certbot python3-certbot-nginx

# ── 2. Deploy user ─────────────────────────────────────────────────
echo "==> Creating deploy user '$APP_USER'"
id "$APP_USER" &>/dev/null || useradd -r -m -s /bin/bash "$APP_USER"
# Allow user to restart own service via sudo (for GitHub Actions deploy)
SUDOERS_LINE="$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart $SERVICE"
grep -qF "$SUDOERS_LINE" /etc/sudoers 2>/dev/null || echo "$SUDOERS_LINE" >> /etc/sudoers

# ── 3. Copy files ──────────────────────────────────────────────────
echo "==> Copying app to $DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"
rsync -a --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
      --exclude 'venv' --exclude '*.pkl' \
      "$REPO_DIR/" "$DEPLOY_DIR/"
chown -R "$APP_USER:$APP_USER" "$DEPLOY_DIR"

# ── 4. Python venv ─────────────────────────────────────────────────
echo "==> Creating Python virtualenv"
sudo -u "$APP_USER" python3 -m venv "$VENV"
sudo -u "$APP_USER" "$VENV/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$VENV/bin/pip" install -q -r "$DEPLOY_DIR/dashboard/backend/requirements.txt"

# ── 5. Data directory + config seed ────────────────────────────────
echo "==> Setting up data directory"
DATA_DIR="$DEPLOY_DIR/data"
mkdir -p "$DATA_DIR"
# Seed config from repo defaults if not already present
for f in config.json screening_config.json; do
  [ -f "$DATA_DIR/$f" ] || cp "$DEPLOY_DIR/dashboard/backend/$f" "$DATA_DIR/$f"
done
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"

# ── 6. DB migration ────────────────────────────────────────────────
echo "==> Running DB migration (pickle + CSV → SQLite)"
sudo -u "$APP_USER" DATA_DIR="$DATA_DIR" \
  "$VENV/bin/python3" "$DEPLOY_DIR/scripts/migrate_to_db.py" \
  --db "$DATA_DIR/dashboard.db" || echo "  (migration skipped — run manually if needed)"

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
# Uncomment to protect write endpoints:
# Environment=DASHBOARD_SECRET=change-me

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"
echo "  Service started. Status:"
systemctl is-active "$SERVICE" && echo "  ✓ running" || echo "  ✗ failed (check: journalctl -u $SERVICE)"

# ── 9. nginx ───────────────────────────────────────────────────────
echo "==> Configuring nginx"
NGINX_CONF="$DEPLOY_DIR/nginx/nginx.conf"
if [ -n "$DOMAIN" ]; then
  sed "s/YOUR_DOMAIN/$DOMAIN/g" "$NGINX_CONF" \
    > /etc/nginx/sites-available/etf-dashboard
else
  # No domain: bind to _ (all hosts), HTTP only
  sed 's/server_name YOUR_DOMAIN/server_name _/' "$NGINX_CONF" \
    > /etc/nginx/sites-available/etf-dashboard
fi
ln -sf /etc/nginx/sites-available/etf-dashboard \
        /etc/nginx/sites-enabled/etf-dashboard
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 10. HTTPS (optional) ───────────────────────────────────────────
if [ -n "$DOMAIN" ]; then
  echo ""
  echo "==> Let's Encrypt certificate for $DOMAIN"
  echo "    (DNS A-record must already point to this server)"
  read -r -p "    Issue certificate now? [y/N] " yn
  if [[ "${yn:-n}" =~ ^[Yy]$ ]]; then
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
      -m "admin@$DOMAIN" --redirect
    # Add renewal to cron
    (crontab -l 2>/dev/null | grep -v certbot; \
     echo "0 3 * * * certbot renew --quiet && nginx -s reload") | crontab -
    echo "  ✓ HTTPS enabled, renewal cron set"
  fi
fi

# ── 11. SSH key for GitHub Actions ─────────────────────────────────
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
echo " NEXT STEP — add these 3 GitHub repo secrets:  "
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Secret name: VPS_HOST"
echo "  Value:       $(curl -s ifconfig.me 2>/dev/null || echo '<server-ip>')"
echo ""
echo "  Secret name: VPS_USER"
echo "  Value:       $APP_USER"
echo ""
echo "  Secret name: VPS_SSH_KEY"
echo "  Value (paste the PRIVATE key below):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat "$KEY_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✓ Setup complete!"
echo ""
echo "  Dashboard: http://${DOMAIN:-$(curl -s ifconfig.me 2>/dev/null)}:80"
echo ""
echo "  Useful commands:"
echo "    journalctl -u $SERVICE -f        # live logs"
echo "    systemctl restart $SERVICE       # manual restart"
echo "    DATA_DIR=$DATA_DIR $VENV/bin/python3 $DEPLOY_DIR/dashboard/backend/engine.py"
echo ""
echo "  PPM quarterly update:"
echo "    curl -X POST http://${DOMAIN:-localhost}/api/import-ppm \\"
echo "      -F 'file=@Fondandelskurser_Q2_2026.xlsx'"
