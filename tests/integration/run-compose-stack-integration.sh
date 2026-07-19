#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
PROJECT_NAME="decentralabs-gateway-integration-$$"
TIMEOUT_SECONDS="${COMPOSE_STACK_TEST_TIMEOUT_SECONDS:-600}"

compose() {
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
}

print_diagnostics() {
  echo "--- Compose status ---" >&2
  compose ps >&2 || true
  echo "--- Compose logs ---" >&2
  compose logs --no-color --tail=200 mysql blockchain-services guacamole ops-worker >&2 || true
}

cleanup() {
  local exit_code=$?
  if [[ "$exit_code" -ne 0 ]]; then
    print_diagnostics
  fi
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  exit "$exit_code"
}
trap cleanup EXIT

if [[ ! -f "$ROOT_DIR/.env" || ! -f "$ROOT_DIR/blockchain-services/.env" ]]; then
  echo "This test requires a configured Lab Gateway .env and blockchain-services/.env." >&2
  echo "Run setup.sh/setup.bat first, then rerun this integration test." >&2
  exit 2
fi

wait_for_healthy() {
  local service="$1"
  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  local container_id=""
  local health_status=""

  echo "Waiting for $service to become healthy..."
  while (( SECONDS < deadline )); do
    container_id="$(compose ps -q "$service" 2>/dev/null || true)"
    if [[ -n "$container_id" ]]; then
      health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$container_id" 2>/dev/null || true)"
      case "$health_status" in
        healthy)
          echo "$service is healthy"
          return 0
          ;;
        unhealthy)
          echo "$service is unhealthy" >&2
          return 1
          ;;
        no-healthcheck)
          echo "$service has no healthcheck" >&2
          return 1
          ;;
      esac
    fi
    sleep 5
  done

  echo "Timed out waiting for $service to become healthy" >&2
  return 1
}

echo "Starting the real Lab Gateway database-dependent services..."
compose up --build --detach mysql blockchain-services guacamole ops-worker

wait_for_healthy mysql
wait_for_healthy blockchain-services
wait_for_healthy guacamole
wait_for_healthy ops-worker

echo "Real Compose stack readiness checks passed."
