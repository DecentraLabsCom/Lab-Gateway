#!/usr/bin/env bash
# =================================================================
# FMU Integration Test Suite for DecentraLabs Gateway
# Tests FMU Runner routing, authentication, concurrency, and timeout
# =================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.fmu-integration.yml"
CERTS_DIR="$SCRIPT_DIR/certs"
PASSED=0
FAILED=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

function cleanup {
  echo -e "\n${YELLOW}Cleaning up...${NC}"
  docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
}

trap cleanup EXIT

# Generate test certificates if needed
if [ ! -f "$CERTS_DIR/privkey.pem" ] || [ ! -f "$CERTS_DIR/fullchain.pem" ] || [ ! -f "$CERTS_DIR/public_key.pem" ]; then
  echo -e "${YELLOW}Generating test certificates...${NC}"
  chmod +x "$CERTS_DIR/generate-certs.sh"
  "$CERTS_DIR/generate-certs.sh"
fi

function log_pass {
  echo -e "${GREEN}✓ PASS${NC}: $1"
  PASSED=$((PASSED + 1))
}

function log_fail {
  echo -e "${RED}✗ FAIL${NC}: $1"
  FAILED=$((FAILED + 1))
}

function wait_for_service {
  local url=$1
  local max_attempts=${2:-30}
  local attempt=0
  while [ $attempt -lt $max_attempts ]; do
    if curl -sk "$url" >/dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  return 1
}

echo "=================================================="
echo "DecentraLabs Gateway — FMU Integration Tests"
echo "=================================================="

# Start services
echo -e "\n${YELLOW}Starting services (OpenResty + mocks + FMU Runner)...${NC}"
docker compose -f "$COMPOSE_FILE" up --build -d

PORT=18443
BASE_URL="https://127.0.0.1:${PORT}"
AUTH_HEADER="Authorization: Bearer integration-test-jwt"

echo "Waiting for services to be ready..."
if ! wait_for_service "${BASE_URL}/fmu/health" 90; then
  echo -e "${RED}Services failed to start${NC}"
  docker compose -f "$COMPOSE_FILE" logs
  exit 1
fi

# Also wait for fmu-runner mock to be reachable through OpenResty
# (DNS resolution may take a moment with the variable-based proxy_pass)
sleep 3
echo -e "${GREEN}Services ready${NC}\n"

# Reset FMU Runner test state
curl -sk "https://127.0.0.1:${PORT}/fmu/_test/reset" >/dev/null 2>&1 || true

# =================================================================
# Test 1: FMU Runner health accessible through OpenResty
# =================================================================
echo "Test 1: FMU Runner health through gateway"
FMU_HEALTH=$(curl -sk "${BASE_URL}/fmu/health" || echo "error")
if echo "$FMU_HEALTH" | grep -q '"UP"'; then
  log_pass "FMU Runner health accessible through /fmu/health"
else
  log_fail "FMU Runner health not accessible: $FMU_HEALTH"
fi

# =================================================================
# Test 2: Simulation describe endpoint
# =================================================================
echo "Test 2: Simulation describe endpoint"
DESCRIBE_RESPONSE=$(curl -sk -H "$AUTH_HEADER" "${BASE_URL}/fmu/api/v1/simulations/describe?fmuFileName=test.fmu" || echo "error")
if echo "$DESCRIBE_RESPONSE" | grep -q '"fmiVersion"'; then
  log_pass "Describe endpoint returns FMU metadata"
else
  log_fail "Describe endpoint failed: $DESCRIBE_RESPONSE"
fi

if echo "$DESCRIBE_RESPONSE" | grep -q '"CoSimulation"'; then
  log_pass "Describe reports correct simulation type"
else
  log_fail "Describe missing simulation type: $DESCRIBE_RESPONSE"
fi

if echo "$DESCRIBE_RESPONSE" | grep -q '"modelVariables"'; then
  log_pass "Describe includes model variables"
else
  log_fail "Describe missing model variables: $DESCRIBE_RESPONSE"
fi

# =================================================================
# Test 3: Simulation run endpoint (POST with JSON body)
# =================================================================
echo "Test 3: Simulation run endpoint"
RUN_RESPONSE=$(curl -sk -X POST "${BASE_URL}/fmu/api/v1/simulations/run" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"labId":"lab-1","parameters":{"mass":1.5},"options":{"startTime":0,"stopTime":10,"stepSize":0.01}}' \
  || echo "error")
if echo "$RUN_RESPONSE" | grep -q '"completed"'; then
  log_pass "Run endpoint executes simulation and returns results"
else
  log_fail "Run endpoint failed: $RUN_RESPONSE"
fi

if echo "$RUN_RESPONSE" | grep -q '"position"'; then
  log_pass "Run results contain output variables"
else
  log_fail "Run results missing output variables: $RUN_RESPONSE"
fi

# =================================================================
# Test 4: Describe requires fmuFileName parameter
# =================================================================
echo "Test 4: Describe validation — missing fmuFileName"
DESCRIBE_NO_PARAM=$(curl -sk -o /dev/null -w "%{http_code}" -H "$AUTH_HEADER" "${BASE_URL}/fmu/api/v1/simulations/describe")
if [ "$DESCRIBE_NO_PARAM" = "422" ]; then
  log_pass "Describe rejects request without fmuFileName (422)"
else
  log_fail "Describe should return 422 without fmuFileName, got: $DESCRIBE_NO_PARAM"
fi

# =================================================================
# Test 5: Run with invalid JSON body — 400
# =================================================================
echo "Test 5: Run validation — invalid JSON"
RUN_BAD_JSON=$(curl -sk -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/fmu/api/v1/simulations/run" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d 'not-json')
if [ "$RUN_BAD_JSON" = "400" ] || [ "$RUN_BAD_JSON" = "422" ]; then
  log_pass "Run rejects invalid JSON body ($RUN_BAD_JSON)"
else
  log_fail "Run should reject invalid JSON, got: $RUN_BAD_JSON"
fi

# =================================================================
# Test 6: Concurrency limit — MAX_CONCURRENT_PER_MODEL = 2
# Three simultaneous requests to the same labId; third should get 429
# =================================================================
echo "Test 6: Concurrency limit enforcement"
# Reset state
curl -sk "${BASE_URL}/fmu/_test/reset" >/dev/null 2>&1 || true

# Set the mock to process slowly (50ms internal delay) — enough to overlap concurrent requests
RUN_BODY='{"labId":"conc-test","parameters":{},"options":{"startTime":0,"stopTime":1,"stepSize":0.1}}'

# Fire 3 concurrent requests
STATUS_1=""
STATUS_2=""
STATUS_3=""

curl -sk -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/fmu/api/v1/simulations/run" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" -d "$RUN_BODY" > /tmp/fmu_conc_1.txt &
PID1=$!

curl -sk -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/fmu/api/v1/simulations/run" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" -d "$RUN_BODY" > /tmp/fmu_conc_2.txt &
PID2=$!

# Small delay so the first two are in-flight
sleep 0.1

curl -sk -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/fmu/api/v1/simulations/run" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" -d "$RUN_BODY" > /tmp/fmu_conc_3.txt &
PID3=$!

wait $PID1
wait $PID2
wait $PID3

STATUS_1=$(cat /tmp/fmu_conc_1.txt)
STATUS_2=$(cat /tmp/fmu_conc_2.txt)
STATUS_3=$(cat /tmp/fmu_conc_3.txt)

ALL_STATUSES="$STATUS_1 $STATUS_2 $STATUS_3"
COUNT_429=$(echo "$ALL_STATUSES" | tr ' ' '\n' | grep -c "429" || true)
COUNT_200=$(echo "$ALL_STATUSES" | tr ' ' '\n' | grep -c "200" || true)

if [ "$COUNT_429" -ge 1 ] && [ "$COUNT_200" -ge 2 ]; then
  log_pass "Concurrency limit: $COUNT_200 succeeded, $COUNT_429 rejected (429)"
else
  log_fail "Concurrency limit not enforced: statuses=$ALL_STATUSES (expected >=2 x 200, >=1 x 429)"
fi

# =================================================================
# Test 7: Timeout simulation
# =================================================================
echo "Test 7: Simulation timeout"
TIMEOUT_STATUS=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 15 -X POST \
  "${BASE_URL}/fmu/api/v1/simulations/run?simulateTimeout=2" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"labId":"timeout-test","parameters":{},"options":{}}')
if [ "$TIMEOUT_STATUS" = "504" ]; then
  log_pass "Simulation timeout returns 504"
else
  log_fail "Simulation timeout expected 504, got: $TIMEOUT_STATUS"
fi

# =================================================================
# Test 8: Request headers propagated correctly (X-Real-IP, X-Forwarded-For)
# =================================================================
echo "Test 8: Header propagation"
curl -sk "${BASE_URL}/fmu/_test/reset" >/dev/null 2>&1 || true

curl -sk -X POST "${BASE_URL}/fmu/api/v1/simulations/run" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"labId":"header-test","parameters":{},"options":{}}' >/dev/null 2>&1

LOG_RESPONSE=$(curl -sk "${BASE_URL}/fmu/_test/request-log" || echo '{"requests":[]}')
if echo "$LOG_RESPONSE" | grep -qi "x-real-ip\|x-forwarded-for"; then
  log_pass "OpenResty propagates X-Real-IP / X-Forwarded-For to fmu-runner"
else
  log_fail "Headers not propagated: $LOG_RESPONSE"
fi

# =================================================================
# Test 9: URI rewrite — /fmu/path → /path on upstream
# =================================================================
echo "Test 9: URI rewrite (/fmu/ prefix stripped)"
if echo "$LOG_RESPONSE" | grep -q '"/api/v1/simulations/run"'; then
  log_pass "URI correctly rewritten from /fmu/api/... to /api/..."
else
  log_fail "URI not rewritten correctly: $LOG_RESPONSE"
fi

# =================================================================
# Summary
# =================================================================
echo ""
echo "=================================================="
echo "FMU Integration Test Results"
echo "=================================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo "=================================================="

if [ $FAILED -gt 0 ]; then
  exit 1
fi

echo -e "\n${GREEN}All FMU integration tests passed!${NC}"
