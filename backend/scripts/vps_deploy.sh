#!/bin/bash
# VPS deploy script — triggered by the /internal/deploy webhook.
# Clones latest code from GitHub and restarts the backend service.
set -e
LOG=/tmp/vps_deploy.log

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== Deploy started ==="

# Clone latest to temp dir
rm -rf /tmp/ek_deploy
git clone --depth=1 https://github.com/ayush229-oss/edgekit.git /tmp/ek_deploy

# Sync backend files
cp -a /tmp/ek_deploy/backend/. /opt/edgekit/backend/
cp /tmp/ek_deploy/pyproject.toml /opt/edgekit/pyproject.toml
rm -rf /tmp/ek_deploy

log "Files synced"

# Install new deps quietly
pip install sentry-sdk pyarrow --break-system-packages -q 2>/dev/null || true

# Restart service (this kills the current process — must run in detached session)
systemctl restart edgekit-backend
sleep 5
systemctl is-active edgekit-backend && log "Service is active" || log "WARNING: service not active after restart"

log "=== Deploy complete ==="
