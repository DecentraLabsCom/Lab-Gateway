#!/usr/bin/env bash
set -Eeuo pipefail

# Validate the three supported deployment topologies without starting services
# or reading/writing a developer's .env files.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

ROOT_ENV_FILE="$TEMP_DIR/root.env"
BACKEND_ENV_FILE="$TEMP_DIR/blockchain-services.env"
cp "$ROOT_DIR/.env.example" "$ROOT_ENV_FILE"
cp "$ROOT_DIR/blockchain-services/.env.example" "$BACKEND_ENV_FILE"

compose_gateway_config() {
  local topology="$1"
  local issuer="$2"
  local backend_enabled="$3"

  echo "Validating ${topology} Gateway topology..."
  ISSUER="$issuer" \
  BLOCKCHAIN_SERVICES_ENABLED="$backend_enabled" \
  BLOCKCHAIN_SERVICES_ENV_FILE="$BACKEND_ENV_FILE" \
    docker compose \
      --project-directory "$ROOT_DIR" \
      --env-file "$ROOT_ENV_FILE" \
      -f "$ROOT_DIR/docker-compose.yml" \
      config -q
}

compose_gateway_config "Full" "" "true"
compose_gateway_config "Lite" "https://full.example.edu/auth" "false"

STANDALONE_DIR="$TEMP_DIR/standalone"
mkdir -p "$STANDALONE_DIR"
cp "$ROOT_DIR/blockchain-services/docker-compose.yml" \
  "$STANDALONE_DIR/docker-compose.yml"
cp "$ROOT_DIR/blockchain-services/.env.example" "$STANDALONE_DIR/.env"

echo "Validating standalone blockchain-services topology..."
docker compose \
  --project-directory "$STANDALONE_DIR" \
  --env-file "$STANDALONE_DIR/.env" \
  -f "$STANDALONE_DIR/docker-compose.yml" \
  config -q

echo "Full, Lite, and standalone topology checks passed."
