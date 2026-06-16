#!/bin/bash
# VPS deployment script — run once as root.
# Usage: bash setup.sh /opt/etf-dashboard

set -euo pipefail
DEPLOY_DIR="${1:-/opt/etf-dashboard}"

echo "==> Installing system packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx

echo "==> Copying app files to $DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"
cp -r backend frontend "$DEPLOY_DIR/"
# Ensure data dir exists
mkdir -p "$DEPLOY_DIR/frontend/static"

echo "==> Creating Python virtualenv"
python3 -m venv "$DEPLOY_DIR/venv"
"$DEPLOY_DIR/venv/bin/pip" install -q --upgrade pip
"$DEPLOY_DIR/venv/bin/pip" install -q -r "$DEPLOY_DIR/backend/requirements.txt"

echo "==> Installing systemd service"
cp deploy/etf-dashboard.service /etc/systemd/system/etf-dashboard.service
# Update path in service file
sed -i "s|/opt/etf-dashboard|$DEPLOY_DIR|g" /etc/systemd/system/etf-dashboard.service
systemctl daemon-reload
systemctl enable etf-dashboard
systemctl restart etf-dashboard

echo "==> Configuring nginx"
cp deploy/nginx.conf /etc/nginx/sites-available/etf-dashboard
ln -sf /etc/nginx/sites-available/etf-dashboard /etc/nginx/sites-enabled/etf-dashboard
nginx -t && systemctl reload nginx

echo ""
echo "==> Installing crontab (last weekday of month, 22:00 CET = 21:00 UTC)"
CRON_CMD="0 21 28-31 * * [ \"\$(date +\\%u)\" -le 5 ] && cd $DEPLOY_DIR/backend && $DEPLOY_DIR/venv/bin/python3 engine.py >> /var/log/etf-engine.log 2>&1"
(crontab -l 2>/dev/null | grep -v "etf-dashboard\|engine.py"; echo "$CRON_CMD") | crontab -

echo ""
echo "==> Running initial engine calculation (takes ~1-2 min)"
cd "$DEPLOY_DIR/backend" && "$DEPLOY_DIR/venv/bin/python3" engine.py

echo ""
echo "✓ Done. Dashboard should be live on port 80."
echo "  To enable HTTPS: certbot --nginx -d your-domain.com"
echo "  To set auth secret: edit /etc/systemd/system/etf-dashboard.service"
echo "    → uncomment: Environment=DASHBOARD_SECRET=your-secret"
echo "    → then: systemctl daemon-reload && systemctl restart etf-dashboard"
