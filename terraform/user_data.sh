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

# ── Mount persistent EBS data volume ──────────────────────────────────────────
# The /dev/xvdf volume is attached by Terraform and persists across instance
# replacements — it stores caddy TLS certs and postgres data so they survive.
DATA_DEVICE="/dev/xvdf"
DATA_MOUNT="/data"
if [ -b "$DATA_DEVICE" ]; then
    echo "==> Mounting persistent data volume $DATA_DEVICE → $DATA_MOUNT"
    if ! blkid "$DATA_DEVICE" | grep -q ext4; then
        echo "==> Formatting data volume (first use)"
        mkfs.ext4 -F "$DATA_DEVICE"
    fi
    mkdir -p "$DATA_MOUNT"
    mount "$DATA_DEVICE" "$DATA_MOUNT"
    echo "$DATA_DEVICE $DATA_MOUNT ext4 defaults,nofail 0 2" >> /etc/fstab
    # Restore Docker named volumes from persistent disk if they exist
    mkdir -p "$DATA_MOUNT/caddy_data" "$DATA_MOUNT/caddy_config" "$DATA_MOUNT/postgres_data"
    echo "==> Persistent volume mounted — certs and DB will survive instance replacement"
else
    echo "==> No persistent data volume found — using ephemeral storage"
    DATA_MOUNT=""
fi

echo "==> Cloning repository"
git clone ${repo_url} /app
cd /app

# ── Resolve Public IP and Configure Domain ────────────────────────────────────
IMDS_TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 || true)
if [ -z "$PUBLIC_IP" ]; then
    PUBLIC_IP=$(curl -s https://api.ipify.org || echo "127.0.0.1")
fi

DOMAIN="${domain}"
DUCKDNS_TOKEN="${duckdns_token}"

if echo "$DOMAIN" | grep -q '\.duckdns\.org$' && [ -n "$DUCKDNS_TOKEN" ]; then
    # DuckDNS — extract subdomain and register current IP so HTTPS cert resolves
    DUCK_SUB=$(echo "$DOMAIN" | sed 's/\.duckdns\.org//')
    echo "==> Registering $PUBLIC_IP with DuckDNS subdomain $DUCK_SUB"
    DUCK_RESP=$(curl -s "https://www.duckdns.org/update?domains=$${DUCK_SUB}&token=$${DUCKDNS_TOKEN}&ip=$${PUBLIC_IP}")
    echo "==> DuckDNS response: $DUCK_RESP"
elif [ "$DOMAIN" = "sslip.io" ] || [ -z "$DOMAIN" ]; then
    echo "==> No custom domain — using sslip.io wildcard DNS"
    DOMAIN="$${PUBLIC_IP//./-}.sslip.io"
fi

IP_PLAIN="$PUBLIC_IP"
echo "==> Using domain: $DOMAIN  (IP: $IP_PLAIN)"

echo "==> Writing .env"
cat > /app/.env <<'ENVEOF'
# ── Django ────────────────────────────────────────────────────────────────────
DEBUG=False
LOG_LEVEL=INFO
CHAT_LOG_LEVEL=INFO
DJANGO_SECRET_KEY=${django_secret_key}
ALLOWED_HOSTS=__DOMAIN__,__IP__,localhost,127.0.0.1,backend
CSRF_TRUSTED_ORIGINS=https://__DOMAIN__,http://__IP__
CORS_ALLOWED_ORIGINS=https://__DOMAIN__,http://__IP__

# ── Twilio ────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID=${twilio_account_sid}
TWILIO_AUTH_TOKEN=${twilio_auth_token}
TWILIO_PHONE_NUMBER=${twilio_phone_number}

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY=${gemini_api_key}

# ── Public URL (used by backend to build Twilio WSS callback URLs) ────────────
PUBLIC_URL=https://__DOMAIN__

# ── Frontend — leave blank so window.location.origin is used automatically ───
VITE_API_BASE_URL=
ENVEOF

echo "==> Customizing .env"
sed -i "s/__DOMAIN__/$DOMAIN/g" /app/.env
sed -i "s/__IP__/$IP_PLAIN/g"   /app/.env

echo "==> Writing Caddyfile"
cat > /app/Caddyfile <<'CADDYEOF'
# HTTPS via sslip.io — TLS cert obtained automatically, serves Twilio WSS
__DOMAIN__ {
    handle /ws/* {
        reverse_proxy backend:8000
    }
    handle /media-stream* {
        reverse_proxy backend:8000
    }
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle /admin/* {
        reverse_proxy backend:8000
    }
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
    handle {
        reverse_proxy frontend:5173
    }
}

# HTTP via bare IP — always accessible even when TLS cert is unavailable
http://__IP__ {
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle /admin/* {
        reverse_proxy backend:8000
    }
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
    handle {
        reverse_proxy frontend:5173
    }
}
CADDYEOF

echo "==> Customizing Caddyfile"
sed -i "s/__DOMAIN__/$DOMAIN/g" /app/Caddyfile
sed -i "s/__IP__/$IP_PLAIN/g"   /app/Caddyfile

echo "==> Writing docker-compose.override.yml"
# Bind caddy volumes to persistent disk if available, else use named volumes
if [ -n "$DATA_MOUNT" ]; then
    CADDY_DATA="$DATA_MOUNT/caddy_data"
    CADDY_CONFIG="$DATA_MOUNT/caddy_config"
    POSTGRES_DATA="$DATA_MOUNT/postgres_data"
else
    CADDY_DATA="caddy_data"
    CADDY_CONFIG="caddy_config"
    POSTGRES_DATA="postgres_data"
fi

cat > /app/docker-compose.override.yml <<COMPOSEEOF
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
      - $${CADDY_DATA}:/data
      - $${CADDY_CONFIG}:/config
    depends_on:
      - backend
      - frontend

  db:
    volumes:
      - $${POSTGRES_DATA}:/var/lib/postgresql/data

  redis:
    command: redis-server --maxmemory 150mb --maxmemory-policy allkeys-lru

volumes:
  caddy_data:
  caddy_config:
COMPOSEEOF

echo "==> Building and starting all services"
docker compose up -d --build

echo "==> All services started."
echo "    HTTP  (always) : http://$IP_PLAIN"
echo "    HTTPS (TLS)    : https://$DOMAIN"
echo "    Tail logs      : docker compose -f /app/docker-compose.yml logs -f"
