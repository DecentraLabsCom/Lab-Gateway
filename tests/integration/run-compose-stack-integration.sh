#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
PROJECT_NAME="decentralabs-gateway-integration-$$"
TIMEOUT_SECONDS="${COMPOSE_STACK_TEST_TIMEOUT_SECONDS:-600}"
ROOT_ENV_FILE="${COMPOSE_STACK_ROOT_ENV_FILE:-$ROOT_DIR/.env}"
BACKEND_ENV_FILE="${COMPOSE_STACK_BACKEND_ENV_FILE:-$ROOT_DIR/blockchain-services/.env}"
COMPOSE_OVERRIDE_FILE="${COMPOSE_STACK_OVERRIDE_FILE:-}"
OPENRESTY_URL="${COMPOSE_STACK_OPENRESTY_URL:-https://127.0.0.1:${COMPOSE_STACK_OPENRESTY_PORT:-8443}}"
export BLOCKCHAIN_SERVICES_ENV_FILE="$BACKEND_ENV_FILE"
export COMPOSE_PROFILES="${COMPOSE_STACK_PROFILES:-fmu-runner}"

COMPOSE_ARGS=(-p "$PROJECT_NAME" -f "$COMPOSE_FILE")
if [[ -n "$COMPOSE_OVERRIDE_FILE" ]]; then
  COMPOSE_ARGS+=(-f "$COMPOSE_OVERRIDE_FILE")
fi

compose() {
  docker compose --env-file "$ROOT_ENV_FILE" "${COMPOSE_ARGS[@]}" "$@"
}

print_diagnostics() {
  echo "--- Compose status ---" >&2
  compose ps >&2 || true
  echo "--- Compose logs ---" >&2
  compose logs --no-color --tail=200 mysql blockchain-services guacamole guacd ops-worker openresty fmu-runner >&2 || true
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

if [[ ! -f "$ROOT_ENV_FILE" || ! -f "$BACKEND_ENV_FILE" ]]; then
  echo "This test requires a configured Lab Gateway .env and blockchain-services/.env." >&2
  echo "Root env: $ROOT_ENV_FILE" >&2
  echo "Backend env: $BACKEND_ENV_FILE" >&2
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

wait_for_url() {
  local url="$1"
  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    if curl -kfsS --connect-timeout 3 "$url" -H 'Host: localhost' >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  echo "Timed out waiting for $url" >&2
  return 1
}

mysql_query() {
  local database="$1"
  local sql="$2"
  compose exec -T mysql sh -c \
    'root_password="$(cat /run/secrets/mysql_root_password)"; mysql --protocol=socket -uroot -p"$root_password" "$1" --batch --skip-column-names -e "$2"' \
    sh "$database" "$sql"
}

echo "Starting the real Lab Gateway resilience stack..."
compose up --build --detach mysql blockchain-services guacamole guacd ops-worker fmu-runner openresty

wait_for_healthy mysql
wait_for_healthy blockchain-services
wait_for_healthy guacamole
wait_for_healthy guacd
wait_for_healthy ops-worker
wait_for_healthy fmu-runner
wait_for_healthy openresty

echo "Checking the real OpenResty edge before and after a restart..."
wait_for_url "$OPENRESTY_URL/"
compose restart openresty >/dev/null
wait_for_healthy openresty
wait_for_url "$OPENRESTY_URL/"
echo "OpenResty restart preserved a healthy real edge."

echo "Checking Guacamole history-backed observation reconciliation..."
guacamole_database="$(grep -E '^MYSQL_DATABASE=' "$ROOT_ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d '\r')"
guacamole_database="${guacamole_database:-guacamole_db}"
blockchain_database="$(grep -E '^BLOCKCHAIN_MYSQL_DATABASE=' "$ROOT_ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d '\r')"
blockchain_database="${blockchain_database:-blockchain_services}"

history_table_count="$(mysql_query "$guacamole_database" "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'guacamole_connection_history';")"
if [[ "$history_table_count" != "1" ]]; then
  echo "Guacamole history table is not available in the real schema." >&2
  exit 1
fi

history_user="resilience-history-user"
history_token="resilience-history-token-$$"
history_expires="$(($(date +%s) + 300))"
compose exec -T ops-worker python -c \
  'import json, os, pathlib, requests, sys; token=pathlib.Path("/run/secrets/session_observation_ingest_token").read_text().strip(); payload={"authToken":sys.argv[1],"username":sys.argv[2],"reservationKey":"resilience-history-reservation","jwtJti":"resilience-history-jti","gatewayId":"localhost","expiresAt":int(sys.argv[3])}; response=requests.post("http://127.0.0.1:8081/internal/guacamole-token-revocations", headers={"X-Gateway-Observation-Token":token}, json=payload, timeout=5); print(response.text); response.raise_for_status()' \
  "$history_token" "$history_user" "$history_expires"
history_hash="$(printf '%s' "$history_token" | sha256sum | cut -d' ' -f1)"
mysql_query "$blockchain_database" "UPDATE guacamole_token_revocation_queue SET status = 'REVOKED', expires_at = UTC_TIMESTAMP() + INTERVAL 5 MINUTE WHERE token_hash = '$history_hash';"
mysql_query "$guacamole_database" "INSERT INTO guacamole_connection_history (username, connection_name, start_date, end_date) VALUES ('$history_user', 'resilience-history-connection', UTC_TIMESTAMP(), UTC_TIMESTAMP());"
compose exec -T ops-worker python -c \
  'import worker; worker.requests.get = lambda *args, **kwargs: type("Response", (), {"status_code": 200, "json": lambda self: {}})(); worker._reconcile_guacamole_observations("unused-admin-token", "mysql")'
observation_count="$(mysql_query "$blockchain_database" "SELECT COUNT(*) FROM gateway_session_observation_outbox WHERE dedup_key = '$history_hash' AND access_type = 'guacamole';")"
if [[ "$observation_count" != "1" ]]; then
  echo "Guacamole history did not produce a durable session observation (count=$observation_count)." >&2
  exit 1
fi
echo "Guacamole history produced a durable session observation."

echo "Checking the production FMU runner queue under backpressure..."
compose exec -T fmu-runner python - <<'PY'
import asyncio
from pathlib import Path
from types import SimpleNamespace

from realtime_ws import RealtimeWsManager, _RealtimeSession, _WsConnection


class SlowWebSocket:
    async def send_json(self, _payload):
        await asyncio.sleep(60)


async def main():
    manager = RealtimeWsManager(
        logger=SimpleNamespace(error=lambda *args, **kwargs: None),
        verify_jwt_token=None,
        enforce_fmu_claim=lambda claims: None,
        resolve_fmu_path=lambda access_key: Path('/tmp/' + access_key),
        get_claim_lab_id=lambda claims: 'resilience-lab',
        normalize_lab_id=lambda value: str(value),
        coerce_epoch_seconds=lambda value: int(value) if value is not None else None,
        acquire_slot=lambda lab_id: None,
        release_slot=lambda lab_id: None,
    )
    claims = {'sub': 'resilience-user', 'labId': 'resilience-lab', 'accessKey': 'test.fmu', 'reservationKey': 'resilience-reservation', 'pucHash': 'resilience-puc', 'exp': 4102444800}
    session = _RealtimeSession(manager, 'resilience-session', claims, Path('/tmp/test.fmu'))
    connection = _WsConnection(SlowWebSocket(), queue_size=2)
    session.connection = connection
    await session._enqueue_event({'type': 'event', 'sequence': 1})
    await session._enqueue_event({'type': 'event', 'sequence': 2})
    await session._enqueue_event({'type': 'event', 'sequence': 3})
    values = [connection.queue.get_nowait()['sequence'] for _ in range(2)]
    assert values == [2, 3], values
    assert session._pending_queue_drops == 1, session._pending_queue_drops


asyncio.run(main())
PY
echo "Production FMU runner retained the newest WebSocket events and counted the dropped oldest event."

echo "Real Compose resilience checks passed."
