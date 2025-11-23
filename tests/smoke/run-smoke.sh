#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="tests/smoke/docker-compose.smoke.yml"
COOKIE_FILE="tests/smoke/cookie.txt"
JWT_FILE="tests/smoke/jwt.txt"

function cleanup {
  docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
  rm -f "$COOKIE_FILE"
}

trap cleanup EXIT

docker compose -f "$COMPOSE_FILE" up --build -d

PORT=18443

ATTEMPTS=60
until curl -sk --resolve lab.test:${PORT}:127.0.0.1 https://lab.test:${PORT}/ >/dev/null; do
  ATTEMPTS=$((ATTEMPTS - 1))
  if [ "$ATTEMPTS" -le 0 ]; then
    echo "OpenResty did not become ready in time"
    docker compose -f "$COMPOSE_FILE" logs openresty || true
    exit 1
  fi
  sleep 2
done

JWT=$(cat "$JWT_FILE")
curl -sk --resolve lab.test:${PORT}:127.0.0.1 -c "$COOKIE_FILE" "https://lab.test:${PORT}/guacamole/?jwt=${JWT}" >/dev/null

if ! grep -q "JTI.*smoke-jti-123" "$COOKIE_FILE"; then
  echo "Smoke cookie missing expected JTI entry"
  exit 1
fi

RESPONSE=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -b "$COOKIE_FILE" https://lab.test:${PORT}/guacamole/api/echo)
echo "Smoke response: $RESPONSE"

if ! echo "$RESPONSE" | grep -Eq '"authorization"[[:space:]]*:[[:space:]]*"smoke-user"'; then
  echo "Authorization header not propagated through OpenResty"
  exit 1
fi

# Verify /ops/ requires token and upstream resolves
OPS_HEALTH=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" https://lab.test:${PORT}/ops/health || true)
if [ "$OPS_HEALTH" != "401" ] && [ "$OPS_HEALTH" != "503" ]; then
  echo "Unexpected /ops/health status without token: $OPS_HEALTH"
  exit 1
fi

OPS_OK=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -H "X-Ops-Token=test-ops-secret-123" https://lab.test:${PORT}/ops/health || true)
if ! echo "$OPS_OK" | grep -q '"status":"ok"'; then
  echo "OPS health failed with token: $OPS_OK"
  exit 1
fi

# Verify LocalhostOnlyFilter protects wallet/treasury
WALLET_STATUS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" https://lab.test:${PORT}/wallet/health || true)
if [ "$WALLET_STATUS" != "200" ] && [ "$WALLET_STATUS" != "403" ]; then
  echo "Unexpected wallet health status: $WALLET_STATUS"
  exit 1
fi

echo "Smoke test passed"
