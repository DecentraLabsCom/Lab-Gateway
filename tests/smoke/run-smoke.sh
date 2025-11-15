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

ATTEMPTS=30
until curl -sk --resolve lab.test:${PORT}:127.0.0.1 https://lab.test:${PORT}/ >/dev/null; do
  ATTEMPTS=$((ATTEMPTS - 1))
  if [ "$ATTEMPTS" -le 0 ]; then
    echo "OpenResty did not become ready in time"
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

if ! echo "$RESPONSE" | grep -q '"authorization":"smoke-user"'; then
  echo "Authorization header not propagated through OpenResty"
  exit 1
fi

echo "Smoke test passed"
