#!/usr/bin/env bash
# Point the running deployment at a domain: rewrites .env and restarts the prod profile.
# Usage (on the server):  bash deploy/switch-domain.sh task-controller.ru
set -euo pipefail

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
  echo "usage: bash deploy/switch-domain.sh <domain>" >&2
  exit 1
fi

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo ".env not found — copy .env.example first" >&2
  exit 1
fi

# Caddy can only issue a certificate once the domain resolves to this server.
resolved="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)"
if [ -z "$resolved" ]; then
  echo "DNS: $DOMAIN does not resolve yet. Wait for the registrar and run this again." >&2
  exit 1
fi
echo "DNS: $DOMAIN -> $resolved"

sed -i \
  -e "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" \
  -e "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=$DOMAIN,localhost,127.0.0.1|" \
  -e "s|^DJANGO_CSRF_TRUSTED_ORIGINS=.*|DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN|" \
  -e "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://$DOMAIN|" \
  .env

docker compose --profile prod up -d

echo "Waiting for the certificate (up to 60 s)…"
for _ in $(seq 1 12); do
  sleep 5
  if curl -fsS --max-time 5 "https://$DOMAIN/api/health/" >/dev/null 2>&1; then
    echo "OK: https://$DOMAIN/api/health/ answers"
    exit 0
  fi
done

echo "Not answering yet. Check: docker compose logs --tail 40 caddy" >&2
exit 1
