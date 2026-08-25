#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.full-lite-integration.yml"
PROJECT_NAME="decentralabs-full-lite-integration-$$"
TMP_DIR="$(mktemp -d)"

FULL_URL="https://127.0.0.1:18443"
LITE_URL="https://127.0.0.1:18444"
CONTROL_URL="http://127.0.0.1:18081"

PASSED=0
FAILED=0

JSON_PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c 'import json' >/dev/null 2>&1; then
    JSON_PYTHON="$candidate"
    break
  fi
done

if [[ -z "$JSON_PYTHON" ]]; then
  echo "A Python interpreter with the standard json module is required" >&2
  exit 1
fi

compose() {
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
}

cleanup() {
  local exit_code=$?
  if [[ "$exit_code" -ne 0 ]]; then
    compose ps >&2 || true
    compose logs --no-color --tail=200 blockchain-services full-gateway lite-gateway ops-full ops-lite >&2 || true
  fi
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$TMP_DIR"
  exit "$exit_code"
}
trap cleanup EXIT

pass() {
  printf '✓ PASS: %s\n' "$1"
  PASSED=$((PASSED + 1))
}

fail() {
  printf '✗ FAIL: %s\n' "$1" >&2
  FAILED=$((FAILED + 1))
}

json_field() {
  local file="$1"
  local field="$2"
  "$JSON_PYTHON" - "$file" "$field" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    value = json.load(stream)
for part in sys.argv[2].split('.'):
    value = value[part]
print(value)
PY
}

wait_for_url() {
  local url="$1"
  local attempts="${2:-60}"
  for _ in $(seq 1 "$attempts"); do
    if curl -fsSk "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

status() {
  curl -sSk -o /dev/null -w '%{http_code}' "$@"
}

assert_status() {
  local expected="$1"
  local name="$2"
  shift 2
  local actual
  actual="$(status "$@")"
  if [[ "$actual" == "$expected" ]]; then
    pass "$name"
  else
    fail "$name (expected $expected, got $actual)"
  fi
}

if [[ ! -s "$SCRIPT_DIR/certs/fullchain.pem" || ! -s "$SCRIPT_DIR/certs/privkey.pem" || ! -s "$SCRIPT_DIR/certs/public_key.pem" ]]; then
  chmod +x "$SCRIPT_DIR/certs/generate-certs.sh"
  "$SCRIPT_DIR/certs/generate-certs.sh" >/dev/null
fi

echo "Starting isolated Full/Lite access stack..."
compose up --build --detach

wait_for_url "$CONTROL_URL/health" || { echo "Control plane did not become ready" >&2; exit 1; }
wait_for_url "$FULL_URL/" || { echo "Full gateway did not become ready" >&2; exit 1; }
wait_for_url "$LITE_URL/" || { echo "Lite gateway did not become ready" >&2; exit 1; }

echo "Checking mode-specific key trust and auth surfaces..."
full_key_hash="$(curl -fsSk "$FULL_URL/.well-known/public-key.pem" -H 'Host: full.local' | sha256sum | awk '{print $1}')"
lite_key_hash="$(curl -fsSk "$LITE_URL/.well-known/public-key.pem" -H 'Host: lite.local' | sha256sum | awk '{print $1}')"
remote_key_hash="$(curl -fsS "$CONTROL_URL/.well-known/public-key.pem" | sha256sum | awk '{print $1}')"
if [[ "$full_key_hash" == "$remote_key_hash" && "$lite_key_hash" == "$remote_key_hash" ]]; then
  pass "Full and Lite expose the control-plane signing key; Lite synchronized the remote key"
else
  fail "Full/Lite key trust mismatch: full=$full_key_hash lite=$lite_key_hash remote=$remote_key_hash"
fi

assert_status 200 "Full keeps local auth endpoints available" \
  "$FULL_URL/auth/message" -H 'Host: full.local'
assert_status 403 "Lite blocks /auth/message" \
  "$LITE_URL/auth/message" -H 'Host: lite.local'
assert_status 403 "Lite blocks /auth/jwks even when the remote issuer exposes JWKS" \
  "$LITE_URL/auth/jwks" -H 'Host: lite.local'
assert_status 403 "Lite blocks direct access-code redemption through /auth/**" \
  "$LITE_URL/auth/access-code/redeem" -H 'Host: lite.local' \
  -X POST -H 'Content-Type: application/json' --data '{}'

echo "Checking the on-chain authorization gate before access-code delivery..."
curl -fsS -X POST "$CONTROL_URL/test/contract-state" \
  -H 'Content-Type: application/json' -d '{"status":1}' > "$TMP_DIR/state-confirmed.json"
curl -sS -o "$TMP_DIR/pending.json" -w '%{http_code}' -X POST "$CONTROL_URL/auth/access-credential" \
  -H 'Content-Type: application/json' \
  -d '{"marketplaceToken":"integration-marketplace-token","gatewayId":"lite.local","gatewayOrigin":"https://lite.local","reservationKey":"reservation-access-authorized","labId":"42"}' \
  > "$TMP_DIR/pending.status"
if [[ "$(<"$TMP_DIR/pending.status")" == "503" ]] \
  && grep -q 'ACCESS_AUTHORIZATION_PENDING' "$TMP_DIR/pending.json"; then
  pass "Control plane withholds access-code while reservation is CONFIRMED"
else
  fail "Access-code was not blocked before ACCESS_AUTHORIZED: status=$(<"$TMP_DIR/pending.status") body=$(<"$TMP_DIR/pending.json")"
fi

curl -fsS -X POST "$CONTROL_URL/test/contract-state" \
  -H 'Content-Type: application/json' -d '{"status":4}' > "$TMP_DIR/state-cancelled.json"
curl -sS -o "$TMP_DIR/rejected.json" -w '%{http_code}' -X POST "$CONTROL_URL/auth/access-credential" \
  -H 'Content-Type: application/json' \
  -d '{"marketplaceToken":"integration-marketplace-token","gatewayId":"lite.local","gatewayOrigin":"https://lite.local","reservationKey":"reservation-rejected","labId":"42"}' \
  > "$TMP_DIR/rejected.status"
if [[ "$(<"$TMP_DIR/rejected.status")" == "409" ]] \
  && grep -q 'ACCESS_AUTHORIZATION_REJECTED' "$TMP_DIR/rejected.json"; then
  pass "Control plane rejects access-code delivery for a terminal reservation state"
else
  fail "Terminal contract state was not rejected: status=$(<"$TMP_DIR/rejected.status") body=$(<"$TMP_DIR/rejected.json")"
fi

curl -fsS -X POST "$CONTROL_URL/test/contract-state" \
  -H 'Content-Type: application/json' -d '{"status":2}' > "$TMP_DIR/state-authorized.json"
if grep -q 'ACCESS_AUTHORIZED' "$TMP_DIR/state-authorized.json"; then
  pass "Contract fixture transitions to ACCESS_AUTHORIZED"
else
  fail "Contract fixture did not report ACCESS_AUTHORIZED"
fi

issue_code() {
  local gateway="$1"
  local origin="$2"
  local output="$3"
  local resource_type="${4:-lab}"
  curl -fsS -X POST "$CONTROL_URL/auth/access-credential" \
    -H 'Content-Type: application/json' \
    -d "{\"marketplaceToken\":\"integration-marketplace-token\",\"gatewayId\":\"$gateway\",\"gatewayOrigin\":\"$origin\",\"reservationKey\":\"reservation-access-authorized-$gateway\",\"labId\":\"42\",\"resourceType\":\"$resource_type\"}" \
    > "$output"
  json_field "$output" accessCode
}

full_code="$(issue_code full.local https://full.local "$TMP_DIR/full-issue.json")"
lite_code="$(issue_code lite.local https://lite.local "$TMP_DIR/lite-issue.json")"
if [[ -n "$full_code" && -n "$lite_code" ]]; then
  pass "ACCESS_AUTHORIZED produces opaque access-codes for Full and Lite"
else
  fail "Access-code delivery returned an empty code"
fi

echo "Checking redemption lease expiry and concurrent redemption..."
lease_code="$(issue_code full.local https://full.local "$TMP_DIR/lease-issue.json")"
lease_prepare_status="$(curl -sS -o "$TMP_DIR/lease-prepare.json" -w '%{http_code}' \
  -X POST "$CONTROL_URL/auth/access-code/redeem" \
  -H 'Content-Type: application/json' \
  -H 'X-Gateway-ID: full.local' \
  -H 'X-Access-Code-Redeemer-Token: full-redeemer' \
  -d "{\"accessCode\":\"$lease_code\"}")"
lease_handle="$(json_field "$TMP_DIR/lease-prepare.json" redemptionHandle)"
sleep 3
lease_commit_status="$(curl -sS -o "$TMP_DIR/lease-commit.json" -w '%{http_code}' \
  -X POST "$CONTROL_URL/auth/access-code/redeem/commit" \
  -H 'Content-Type: application/json' \
  -H 'X-Gateway-ID: full.local' \
  -H 'X-Access-Code-Redeemer-Token: full-redeemer' \
  -d "{\"accessCode\":\"$lease_code\",\"redemptionHandle\":\"$lease_handle\"}")"
if [[ "$lease_prepare_status" == "200" && "$lease_commit_status" == "401" ]] \
  && grep -q 'expired redemption lease' "$TMP_DIR/lease-commit.json"; then
  pass "Prepared access-code redemption expires its lease before commit"
else
  fail "Redemption lease did not expire: prepare=$lease_prepare_status commit=$lease_commit_status body=$(<"$TMP_DIR/lease-commit.json")"
fi

concurrent_code="$(issue_code full.local https://full.local "$TMP_DIR/concurrent-issue.json")"
curl -sSk -o /dev/null -w '%{http_code}\n' -c "$TMP_DIR/concurrent-1.cookies" \
  -X POST "$FULL_URL/auth/access" -H 'Host: full.local' \
  --data-urlencode "access_code=$concurrent_code" > "$TMP_DIR/concurrent-1.status" &
concurrent_pid_1=$!
curl -sSk -o /dev/null -w '%{http_code}\n' -c "$TMP_DIR/concurrent-2.cookies" \
  -X POST "$FULL_URL/auth/access" -H 'Host: full.local' \
  --data-urlencode "access_code=$concurrent_code" > "$TMP_DIR/concurrent-2.status" &
concurrent_pid_2=$!
wait "$concurrent_pid_1"
wait "$concurrent_pid_2"
concurrent_statuses="$(cat "$TMP_DIR/concurrent-1.status" "$TMP_DIR/concurrent-2.status")"
concurrent_successes="$(printf '%s\n' "$concurrent_statuses" | grep -c '^303$' || true)"
concurrent_rejections="$(printf '%s\n' "$concurrent_statuses" | grep -c '^502$' || true)"
if [[ "$concurrent_successes" == "1" && "$concurrent_rejections" == "1" ]]; then
  pass "Concurrent redemption permits one prepared hand-off and rejects the duplicate"
else
  fail "Concurrent redemption was not fenced: statuses=$(tr '\n' ' ' < <(cat "$TMP_DIR/concurrent-1.status" "$TMP_DIR/concurrent-2.status"))"
fi

echo "Checking durable FMU access state across an OpenResty restart..."
fmu_code="$(issue_code full.local https://full.local "$TMP_DIR/fmu-issue.json" fmu)"
fmu_access_status="$(curl -sSk -o /dev/null -w '%{http_code}' -c "$TMP_DIR/fmu.cookies" \
  -X POST "$FULL_URL/auth/access" -H 'Host: full.local' \
  --data-urlencode "access_code=$fmu_code")"
fmu_health_before="$(curl -sSk -o /dev/null -w '%{http_code}' "$FULL_URL/fmu/health" \
  -H 'Host: full.local' -b "$TMP_DIR/fmu.cookies")"
compose restart full-gateway >/dev/null
wait_for_url "$FULL_URL/" 45
fmu_health_after="$(curl -sSk -o /dev/null -w '%{http_code}' "$FULL_URL/fmu/health" \
  -H 'Host: full.local' -b "$TMP_DIR/fmu.cookies")"
if [[ "$fmu_access_status" == "204" && "$fmu_health_before" == "200" && "$fmu_health_after" == "200" ]]; then
  pass "FMU access mapping survives an OpenResty restart through durable encrypted state"
else
  fail "FMU mapping was not recovered after restart: access=$fmu_access_status before=$fmu_health_before after=$fmu_health_after"
fi

echo "Checking Station outage and reconnection at the Ops boundary..."
curl -fsS -X POST http://127.0.0.1:15001/api/test/station \
  -H 'Content-Type: application/json' -d '{"available":false}' > "$TMP_DIR/station-down.json"
station_down_status="$(curl -sS -o "$TMP_DIR/station-down-start.json" -w '%{http_code}' \
  -X POST http://127.0.0.1:15001/api/demo/start \
  -H 'X-Ops-Internal-Token: integration-ops-internal-secret' \
  -H 'Content-Type: application/json' \
  -d '{"demoId":"demo:station-outage","labId":"42"}')"
curl -fsS -X POST http://127.0.0.1:15001/api/test/station \
  -H 'Content-Type: application/json' -d '{"available":true}' > "$TMP_DIR/station-up.json"
station_reconnect_status="$(curl -sS -o "$TMP_DIR/station-reconnect-start.json" -w '%{http_code}' \
  -X POST http://127.0.0.1:15001/api/demo/start \
  -H 'X-Ops-Internal-Token: integration-ops-internal-secret' \
  -H 'Content-Type: application/json' \
  -d '{"demoId":"demo:station-reconnect","labId":"42"}')"
if [[ "$station_down_status" == "503" && "$station_reconnect_status" == "200" ]]; then
  pass "Station outage fails closed and a later reconnect is accepted"
else
  fail "Station outage/reconnect handling failed: down=$station_down_status reconnect=$station_reconnect_status"
fi

echo "Checking Full access-code -> JTI -> Guacamole..."
curl -sSk -D "$TMP_DIR/full-access.headers" -o /dev/null -c "$TMP_DIR/full.cookies" \
  -X POST "$FULL_URL/auth/access" -H 'Host: full.local' \
  --data-urlencode "access_code=$full_code" -w '%{http_code}' > "$TMP_DIR/full-access.status"
full_access_status="$(<"$TMP_DIR/full-access.status")"
if [[ "$full_access_status" == "303" ]] && grep -qiE '^Location: .*?/guacamole/' "$TMP_DIR/full-access.headers" \
  && grep -q 'JTI' "$TMP_DIR/full.cookies"; then
  pass "Full redeems a remote access-code, sets JTI and redirects to Guacamole"
else
  fail "Full hand-off failed: status=$full_access_status headers=$(tr '\n' ' ' < "$TMP_DIR/full-access.headers")"
fi

assert_status 200 "Full Guacamole endpoint is reachable with the JTI cookie" \
  "$FULL_URL/guacamole/" -H 'Host: full.local' -b "$TMP_DIR/full.cookies"
curl -fsSk -b "$TMP_DIR/full.cookies" -X POST "$FULL_URL/guacamole/api/tokens" \
  -H 'Host: full.local' -H 'Content-Type: application/x-www-form-urlencoded' --data '' \
  > "$TMP_DIR/full-guac-token.json"
full_guac_token="$(json_field "$TMP_DIR/full-guac-token.json" authToken)"
full_session="$(curl -fsSk -b "$TMP_DIR/full.cookies" -H 'Host: full.local' \
  -H "Guacamole-Token: $full_guac_token" "$FULL_URL/guacamole/api/session")"
if [[ "$full_session" == *"dlabs-res-full-local"* ]]; then
  pass "Full Guacamole token exchange preserves the reservation-scoped principal"
else
  fail "Full Guacamole session did not preserve the reservation principal: $full_session"
fi

echo "Checking Lite remote issuer, observer and provisioner paths..."
curl -sSk -D "$TMP_DIR/lite-access.headers" -o /dev/null -c "$TMP_DIR/lite.cookies" \
  -X POST "$LITE_URL/auth/access" -H 'Host: lite.local' \
  --data-urlencode "access_code=$lite_code" -w '%{http_code}' > "$TMP_DIR/lite-access.status"
lite_access_status="$(<"$TMP_DIR/lite-access.status")"
if [[ "$lite_access_status" == "303" ]] && grep -qiE '^Location: .*?/guacamole/' "$TMP_DIR/lite-access.headers" \
  && grep -q 'JTI' "$TMP_DIR/lite.cookies"; then
  pass "Lite validates a JWT issued by the remote authority and redirects to local Guacamole"
else
  fail "Lite hand-off failed: status=$lite_access_status headers=$(tr '\n' ' ' < "$TMP_DIR/lite-access.headers")"
fi

assert_status 200 "Lite Guacamole endpoint is reachable with the remote JWT JTI cookie" \
  "$LITE_URL/guacamole/" -H 'Host: lite.local' -b "$TMP_DIR/lite.cookies"
curl -fsSk -b "$TMP_DIR/lite.cookies" -X POST "$LITE_URL/guacamole/api/tokens" \
  -H 'Host: lite.local' -H 'Content-Type: application/x-www-form-urlencoded' --data '' \
  > "$TMP_DIR/lite-guac-token.json"
lite_guac_token="$(json_field "$TMP_DIR/lite-guac-token.json" authToken)"
lite_session="$(curl -fsSk -b "$TMP_DIR/lite.cookies" -H 'Host: lite.local' \
  -H "Guacamole-Token: $lite_guac_token" "$LITE_URL/guacamole/api/session")"
if [[ "$lite_session" == *"dlabs-res-lite-local"* ]]; then
  pass "Lite Guacamole token exchange preserves the remote reservation principal"
else
  fail "Lite Guacamole session did not preserve the reservation principal: $lite_session"
fi

provision_status="$(curl -sS -o "$TMP_DIR/provision.json" -w '%{http_code}' \
  -X POST "$CONTROL_URL/test/provision-lite" -H 'Content-Type: application/json' \
  -d '{"selector":"guac:id:7","sessionId":"remote-session-1"}')"
if [[ "$provision_status" == "200" ]] && grep -q '"success"[[:space:]]*:[[:space:]]*true' "$TMP_DIR/provision.json"; then
  pass "Remote control plane provisions a user through the Lite provisioner route"
else
  fail "Remote Lite provisioner flow failed: status=$provision_status body=$(<"$TMP_DIR/provision.json")"
fi

assert_status 401 "Lite provisioner rejects the wrong credential" \
  "$LITE_URL/gateway-provisioner/guacamole/provision" -H 'Host: lite.local' \
  -H 'X-Guacamole-Provisioner-Token: wrong-token' -H 'Content-Type: application/json' \
  --data '{"selector":"guac:id:7","sessionId":"should-fail"}'

observer_json="$TMP_DIR/observer.json"
curl -fsS "$CONTROL_URL/test/observer-token?gatewayId=lite.local" > "$observer_json"
observer_token="$(json_field "$observer_json" token)"
observer_status="$(curl -sSk -o "$TMP_DIR/observer-response.json" -w '%{http_code}' \
  -X POST "$LITE_URL/access-audit/internal/session-observed" -H 'Host: lite.local' \
  -H "Authorization: Bearer $observer_token" -H 'Content-Type: application/json' \
  -d '{"gatewayId":"lite.local","reservationKey":"reservation-access-authorized-lite.local","jwtJti":"jti-observed-by-lite"}')"
if [[ "$observer_status" == "200" ]] && grep -q '"recorded"[[:space:]]*:[[:space:]]*true' "$TMP_DIR/observer-response.json"; then
  pass "Lite submits a scoped observer JWT to the remote control plane"
else
  fail "Observer token flow failed: status=$observer_status body=$(<"$TMP_DIR/observer-response.json")"
fi

assert_status 401 "Observer endpoint rejects an invalid observer JWT" \
  "$LITE_URL/access-audit/internal/session-observed" -H 'Host: lite.local' \
  -H 'Authorization: Bearer not-a-valid-observer-token' -H 'Content-Type: application/json' \
  --data '{"gatewayId":"lite.local","reservationKey":"reservation-access-authorized-lite.local","jwtJti":"jti-invalid"}'

if [[ "$FAILED" -gt 0 ]]; then
  echo "Full/Lite access integration failed: passed=$PASSED failed=$FAILED" >&2
  exit 1
fi

echo "Full/Lite access integration passed: $PASSED checks"
