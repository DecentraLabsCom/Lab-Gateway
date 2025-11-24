#!/bin/sh
# Refresh self-signed TLS certificate by restarting OpenResty.
# Intended to be scheduled every ~85 days when certbot is not configured.

set -e

ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
  # shellcheck source=/dev/null
  . "$ENV_FILE"
fi

if [ -n "${CERTBOT_DOMAINS:-}" ] && [ -n "${CERTBOT_EMAIL:-}" ]; then
  echo "Certbot domains/email configured; skipping self-signed refresh."
  exit 0
fi

echo "Restarting openresty to refresh self-signed certificate..."
docker compose restart openresty
echo "Done."
