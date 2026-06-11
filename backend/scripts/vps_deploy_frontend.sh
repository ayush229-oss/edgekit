#!/bin/bash
# Frontend deploy — triggered by /internal/deploy-frontend webhook.
# Clones latest code, builds Next.js, restarts PM2 process.
set -e
LOG=/tmp/vps_deploy_frontend.log

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== Frontend deploy started ==="

# Clone latest to temp dir
rm -rf /tmp/ek_deploy_fe
git clone --depth=1 https://github.com/ayush229-oss/edgekit.git /tmp/ek_deploy_fe
log "Cloned repo"

# Sync frontend source (preserve .env.local which is not in git)
rsync -a --delete \
  --exclude='.env.local' \
  --exclude='.next/' \
  --exclude='node_modules/' \
  /tmp/ek_deploy_fe/frontend/ /opt/edgekit/frontend/
rm -rf /tmp/ek_deploy_fe
log "Source synced"

cd /opt/edgekit/frontend

# Install deps
npm ci --prefer-offline --loglevel=warn
log "Dependencies installed"

# Build (env vars read from .env.local)
npm run build
log "Build complete"

# Restart (or start) via PM2
if pm2 describe edgekit-frontend > /dev/null 2>&1; then
  pm2 restart edgekit-frontend --update-env
else
  pm2 start "node_modules/.bin/next start -p 3000" --name edgekit-frontend
  pm2 save
fi

sleep 3
pm2 describe edgekit-frontend | grep -q "online" && log "Frontend is online" || log "WARNING: frontend not online"

log "=== Frontend deploy complete ==="
