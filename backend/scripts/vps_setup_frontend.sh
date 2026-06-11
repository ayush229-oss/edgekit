#!/bin/bash
# One-time setup — run this ONCE on the VPS to prepare it for frontend hosting.
# After this, all future deploys go through vps_deploy_frontend.sh automatically.
set -e

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "=== Frontend VPS setup ==="

# ── Node.js 20 LTS ────────────────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
  log "Installing Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
else
  log "Node.js already installed: $(node -v)"
fi

# ── PM2 ───────────────────────────────────────────────────────────────────────
if ! command -v pm2 &>/dev/null; then
  log "Installing PM2..."
  npm install -g pm2
  pm2 startup systemd -u root --hp /root
else
  log "PM2 already installed: $(pm2 -v)"
fi

# ── Deploy script permissions ─────────────────────────────────────────────────
chmod +x /opt/edgekit/scripts/vps_deploy_frontend.sh
log "Deploy script made executable"

# ── Initial build ─────────────────────────────────────────────────────────────
log "Running initial build (this takes ~2-3 minutes)..."
cd /opt/edgekit/frontend
npm ci --prefer-offline --loglevel=warn
npm run build

# Start PM2 process
pm2 start "node_modules/.bin/next start -p 3000" --name edgekit-frontend
pm2 save
log "PM2 process started"

# ── Nginx config ──────────────────────────────────────────────────────────────
log "Writing nginx config..."
cat > /etc/nginx/sites-available/edgekit-frontend <<'NGINX'
server {
    listen 80;
    server_name edgekit.uk www.edgekit.uk;

    location / {
        proxy_pass         http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection 'upgrade';
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/edgekit-frontend /etc/nginx/sites-enabled/edgekit-frontend
nginx -t && systemctl reload nginx
log "Nginx configured"

# ── SSL via certbot ───────────────────────────────────────────────────────────
log "Getting SSL certificate..."
if ! command -v certbot &>/dev/null; then
  apt-get install -y certbot python3-certbot-nginx
fi
certbot --nginx -d edgekit.uk -d www.edgekit.uk --non-interactive --agree-tos -m ayush229@gmail.com
log "SSL certificate installed"

log ""
log "=== Setup complete ==="
log "Next.js is running on :3000, nginx proxies edgekit.uk → :3000"
log "Future deploys: CI calls POST /internal/deploy-frontend automatically"
log ""
log "IMPORTANT: Make sure /opt/edgekit/frontend/.env.local exists with all env vars."
log "Copy them from Vercel dashboard before the next deploy."
