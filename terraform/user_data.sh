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

# ── Resolve Dynamic sslip.io Domain ───────────────────────────────────────────
DOMAIN="${domain}"
if [ "$DOMAIN" = "sslip.io" ] || [ "$DOMAIN" = "yourname.duckdns.org" ] || [ -z "$DOMAIN" ]; then
    echo "==> Resolving public IP address for sslip.io domain"
    TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
    PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 || true)
    if [ -z "$PUBLIC_IP" ]; then
        PUBLIC_IP=$(curl -s https://api.ipify.org || echo "127.0.0.1")
    fi
    DOMAIN="$${PUBLIC_IP//./-}.sslip.io"
fi
echo "==> Using domain: $DOMAIN"

echo "==> Writing .env"
# Strictly quoted heredoc to prevent shell expansion of random characters (like $w) in django_secret_key
cat > /app/.env <<'ENVEOF'
# ── Django ────────────────────────────────────────────────────────────────────
DEBUG=False
LOG_LEVEL=INFO
CHAT_LOG_LEVEL=INFO
DJANGO_SECRET_KEY=${django_secret_key}
ALLOWED_HOSTS=__DOMAIN__,localhost,127.0.0.1,backend
CSRF_TRUSTED_ORIGINS=https://__DOMAIN__
CORS_ALLOWED_ORIGINS=https://__DOMAIN__

# ── Twilio ────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID=${twilio_account_sid}
TWILIO_AUTH_TOKEN=${twilio_auth_token}
TWILIO_PHONE_NUMBER=${twilio_phone_number}

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY=${gemini_api_key}

# ── Public URL (used by backend to build Twilio callback URLs) ────────────────
PUBLIC_URL=https://__DOMAIN__

# ── Frontend ──────────────────────────────────────────────────────────────────
VITE_API_BASE_URL=https://__DOMAIN__
ENVEOF

echo "==> Customizing .env domain"
sed -i "s/__DOMAIN__/$DOMAIN/g" /app/.env

echo "==> Writing Caddyfile"
cat > /app/Caddyfile <<'CADDYEOF'
__DOMAIN__ {
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

echo "==> Customizing Caddyfile domain"
sed -i "s/__DOMAIN__/$DOMAIN/g" /app/Caddyfile

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
echo "    App URL   : https://$DOMAIN"
