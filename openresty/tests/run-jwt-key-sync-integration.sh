#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENRESTY_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$OPENRESTY_DIR")"

TEMP_ROOT="${PROJECT_ROOT}/.tmp-jwt-key-sync-test"
NETWORK_NAME="lgw-key-sync-test-net"
KEYSERVER_CONTAINER="lgw-key-sync-keysrv"
LITE_CONTAINER="lgw-key-sync-lite"

cleanup() {
    docker rm -f "$LITE_CONTAINER" >/dev/null 2>&1 || true
    docker rm -f "$KEYSERVER_CONTAINER" >/dev/null 2>&1 || true
    docker network rm "$NETWORK_NAME" >/dev/null 2>&1 || true
    rm -rf "$TEMP_ROOT"
}
trap cleanup EXIT

docker version >/dev/null

echo "Building OpenResty image..."
docker compose -f "${PROJECT_ROOT}/docker-compose.yml" build openresty >/dev/null

mkdir -p "${TEMP_ROOT}/keysrv/.well-known" "${TEMP_ROOT}/lite-certs"
cp "${PROJECT_ROOT}/certs/fullchain.pem" "${TEMP_ROOT}/lite-certs/fullchain.pem"
cp "${PROJECT_ROOT}/certs/privkey.pem" "${TEMP_ROOT}/lite-certs/privkey.pem"
cp "${PROJECT_ROOT}/certs/public_key.pem" "${TEMP_ROOT}/keysrv/.well-known/public-key.pem"

# Prepare a deliberately wrong key in lite-certs to verify replacement.
docker run --rm \
    -v "${TEMP_ROOT}/lite-certs:/w" \
    labgateway-openresty:latest \
    sh -c "openssl genrsa -out /w/alt_private.pem 2048 >/dev/null 2>&1 && openssl rsa -in /w/alt_private.pem -pubout -out /w/public_key.pem >/dev/null 2>&1 && rm -f /w/alt_private.pem" >/dev/null

before_hash="$(sha256sum "${TEMP_ROOT}/lite-certs/public_key.pem" | awk '{print $1}')"

docker network create "$NETWORK_NAME" >/dev/null
docker run -d --name "$KEYSERVER_CONTAINER" --network "$NETWORK_NAME" \
    -v "${TEMP_ROOT}/keysrv:/srv:ro" \
    python:3.12-alpine \
    sh -c "cd /srv && python -m http.server 8000" >/dev/null

docker run -d --name "$LITE_CONTAINER" --network "$NETWORK_NAME" \
    --add-host blockchain-services:127.0.0.1 \
    --add-host guacamole:127.0.0.1 \
    --add-host guacd:127.0.0.1 \
    --add-host mysql:127.0.0.1 \
    --add-host ops-worker:127.0.0.1 \
    -e GUAC_ADMIN_USER=admin \
    -e GUAC_ADMIN_PASS=TestPass_12345 \
    -e SERVER_NAME=lite.local \
    -e HTTPS_PORT=443 \
    -e HTTP_PORT=80 \
    -e ISSUER="http://${KEYSERVER_CONTAINER}:8000/auth" \
    -v "${TEMP_ROOT}/lite-certs:/etc/ssl/private" \
    -v "${PROJECT_ROOT}/openresty/nginx.conf:/usr/local/openresty/nginx/conf/nginx.conf:ro" \
    -v "${PROJECT_ROOT}/openresty/lab_access.conf:/etc/openresty/lab_access.conf:ro" \
    -v "${PROJECT_ROOT}/openresty/lua:/etc/openresty/lua:ro" \
    -v "${PROJECT_ROOT}/web:/var/www/html:ro" \
    labgateway-openresty:latest >/dev/null

ready=false
for _ in $(seq 1 30); do
    logs="$(docker logs "$LITE_CONTAINER" 2>&1 || true)"
    if echo "$logs" | grep -q "JWT public key ready for external issuer mode"; then
        ready=true
        break
    fi
    sleep 1
done

if [ "$ready" != "true" ]; then
    echo "Lite container did not report JWT key sync readiness."
    exit 1
fi

expected_hash="$(sha256sum "${TEMP_ROOT}/keysrv/.well-known/public-key.pem" | awk '{print $1}')"
after_hash="$(sha256sum "${TEMP_ROOT}/lite-certs/public_key.pem" | awk '{print $1}')"

if [ "$before_hash" = "$expected_hash" ]; then
    echo "Precondition failed: lite key must start different from issuer key."
    exit 1
fi

if [ "$after_hash" != "$expected_hash" ]; then
    echo "Lite key was not synchronized from issuer key."
    exit 1
fi

echo "JWT key sync integration test passed."
echo "before=${before_hash}"
echo "after=${after_hash}"
echo "expected=${expected_hash}"
