#!/bin/bash
set -euo pipefail
exec > /var/log/user-data.log 2>&1

echo "==> Adding 1 GB swap (prevents OOM during Docker image builds on t4g.micro)"
fallocate -l 1G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

echo "==> Installing system packages"
apt-get update -y
apt-get install -y git curl ca-certificates gnupg

echo "==> Installing Docker"
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu
systemctl enable docker
systemctl start docker

echo "==> Waiting for Docker daemon to be ready"
until docker info >/dev/null 2>&1; do sleep 1; done

echo "==> Cloning repository"
git clone ${repo_url} /app
cd /app

# NOTE: Terraform substitutes all template placeholders in this file before it
# runs on the instance. Single-quoted heredoc delimiters (<<'EOF') then tell
# bash not to do any further $ expansion on the already-literal values.

echo "==> Writing .env"
cat > /app/.env <<'ENVEOF'
# ── Django ────────────────────────────────────────────────────────────────────
DEBUG=False
LOG_LEVEL=INFO
CHAT_LOG_LEVEL=INFO
DJANGO_SECRET_KEY=${django_secret_key}
ALLOWED_HOSTS=${domain}
CSRF_TRUSTED_ORIGINS=https://${domain}
CORS_ALLOWED_ORIGINS=https://${domain}

# ── Twilio ────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID=${twilio_account_sid}
TWILIO_AUTH_TOKEN=${twilio_auth_token}
TWILIO_PHONE_NUMBER=${twilio_phone_number}

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY=${gemini_api_key}

# ── Public URL (used by backend to build Twilio callback URLs) ────────────────
PUBLIC_URL=https://${domain}

# ── Frontend ──────────────────────────────────────────────────────────────────
VITE_API_BASE_URL=https://${domain}
ENVEOF

echo "==> Writing Caddyfile"
# Routes derived from backend/backend/urls.py and backend/chat/routing.py.
cat > /app/Caddyfile <<'CADDYEOF'
${domain} {
    # ── WebSocket paths (Django Channels) ─────────────────────────────────────
    # /ws/voice/         → VoiceConsumer  (browser ↔ backend)
    # /ws/media-stream/  → TwilioConsumer (legacy alias)
    handle /ws/* {
        reverse_proxy backend:8000
    }

    # /media-stream  /media-stream/  → TwilioConsumer (Twilio Media Streams)
    handle /media-stream* {
        reverse_proxy backend:8000
    }

    # ── Django HTTP routes ────────────────────────────────────────────────────
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle /admin/* {
        reverse_proxy backend:8000
    }
    # Twilio POSTs here when a call starts
    handle /outgoing-call* {
        reverse_proxy backend:8000
    }
    handle /health* {
        reverse_proxy backend:8000
    }
    handle /static/* {
        reverse_proxy backend:8000
    }
    handle /media/* {
        reverse_proxy backend:8000
    }

    # ── React frontend (catch-all) ────────────────────────────────────────────
    handle {
        reverse_proxy frontend:5173
    }
}
CADDYEOF

echo "==> Writing docker-compose.override.yml"
cat > /app/docker-compose.override.yml <<'COMPOSEEOF'
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - backend
      - frontend

  # Cap Redis memory — critical on a 1 GB instance
  redis:
    command: redis-server --maxmemory 150mb --maxmemory-policy allkeys-lru

volumes:
  caddy_data:
  caddy_config:
COMPOSEEOF

echo "==> Building and starting all services"
docker compose up -d --build

echo "==> All services started."
echo "    Tail logs : docker compose -f /app/docker-compose.yml logs -f"
echo "    App URL   : https://${domain}"
