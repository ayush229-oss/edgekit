#!/usr/bin/env bash
# ============================================================
# Edgekit Backend — First-time VPS deploy
# Tested on Ubuntu 20.04 / 22.04 / Debian 11 / 12
#
# Run as root or a sudo user:
#   bash deploy.sh
# ============================================================
set -e

REPO_URL="https://github.com/ayush229-oss/edgekit.git"
APP_DIR="/opt/edgekit"
SERVICE_USER="edgekit"
PORT=8765

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Edgekit Backend — VPS Deployment   ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. System packages ────────────────────────────────────────
echo "▶ Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git curl ufw

# ── 2. Create a dedicated system user ─────────────────────────
echo "▶ Creating service user '$SERVICE_USER'..."
id -u "$SERVICE_USER" &>/dev/null || useradd --system --no-create-home "$SERVICE_USER"

# ── 3. Clone or update repo ───────────────────────────────────
echo "▶ Cloning repo to $APP_DIR..."
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

# ── 4. Python venv + dependencies ────────────────────────────
echo "▶ Creating Python virtual environment..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/.venv/bin/pip" install -e "$APP_DIR[api]" --quiet
"$APP_DIR/.venv/bin/pip" install anthropic openai yfinance --quiet

echo "▶ Packages installed:"
"$APP_DIR/.venv/bin/pip" show fastapi uvicorn anthropic openai yfinance \
    | grep -E "^(Name|Version)" | paste - -

# ── 5. systemd service ────────────────────────────────────────
echo "▶ Creating systemd service..."
cat > /etc/systemd/system/edgekit-backend.service << EOF
[Unit]
Description=Edgekit FastAPI Backend
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/uvicorn backend.api.main:app \\
    --host 0.0.0.0 \\
    --port $PORT \\
    --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable edgekit-backend
systemctl restart edgekit-backend

# ── 6. Firewall ───────────────────────────────────────────────
echo "▶ Opening port $PORT in firewall..."
ufw allow "$PORT/tcp" comment "Edgekit backend" 2>/dev/null || true
ufw --force enable 2>/dev/null || true

# ── 7. Health check ───────────────────────────────────────────
echo "▶ Waiting for backend to start..."
sleep 4
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/healthz" || echo "000")

echo ""
echo "══════════════════════════════════════"
if [ "$HTTP_STATUS" = "200" ]; then
    echo "  ✅ Backend is running on port $PORT"
    curl -s "http://localhost:$PORT/healthz"
    echo ""
else
    echo "  ⚠  Health check got HTTP $HTTP_STATUS"
    echo "  Check logs: journalctl -u edgekit-backend -n 30"
fi
echo ""
echo "  Public URL:  http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP'):$PORT"
echo "  Logs:        journalctl -u edgekit-backend -f"
echo "  Restart:     systemctl restart edgekit-backend"
echo "  Update:      bash $APP_DIR/scripts/update.sh"
echo "══════════════════════════════════════"
