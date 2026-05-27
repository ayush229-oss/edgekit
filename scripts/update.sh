#!/usr/bin/env bash
# ============================================================
# Edgekit Backend — Update to latest code
# Run after pushing new commits to GitHub:
#   bash /opt/edgekit/scripts/update.sh
# ============================================================
set -e

APP_DIR="/opt/edgekit"

echo "▶ Pulling latest code..."
git -C "$APP_DIR" pull --ff-only

echo "▶ Updating dependencies..."
"$APP_DIR/.venv/bin/pip" install -e "$APP_DIR[api]" --quiet
"$APP_DIR/.venv/bin/pip" install anthropic openai yfinance --quiet

echo "▶ Restarting service..."
systemctl restart edgekit-backend
sleep 3

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/healthz || echo "000")
if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ Updated and running."
    curl -s http://localhost:8765/healthz
    echo ""
else
    echo "⚠  Service unhealthy after update (HTTP $HTTP_STATUS)"
    echo "Check: journalctl -u edgekit-backend -n 30"
fi
