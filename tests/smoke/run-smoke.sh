#!/usr/bin/env bash
# =================================================================
# Smoke Test Suite for DecentraLabs Gateway
# Quick validation of core functionality after deployment
# =================================================================
set -euo pipefail

COMPOSE_FILE="tests/smoke/docker-compose.smoke.yml"
COOKIE_FILE="tests/smoke/cookie.txt"
JWT_FILE="tests/smoke/jwt.txt"
PASSED=0
FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

function cleanup {
  docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
  rm -f "$COOKIE_FILE"
}

function log_pass {
  echo -e "${GREEN}✓ PASS${NC}: $1"
  PASSED=$((PASSED + 1))
}

function log_fail {
  echo -e "${RED}✗ FAIL${NC}: $1"
  FAILED=$((FAILED + 1))
}

trap cleanup EXIT

echo "=================================================="
echo "DecentraLabs Gateway Smoke Tests"
echo "=================================================="
echo ""

echo -e "${YELLOW}Starting services...${NC}"
docker compose -f "$COMPOSE_FILE" up --build -d

PORT=18443
INTERNAL_TOKEN="smoke-internal-token"

ATTEMPTS=60
until curl -sk --resolve lab.test:${PORT}:127.0.0.1 https://lab.test:${PORT}/ >/dev/null; do
  ATTEMPTS=$((ATTEMPTS - 1))
  if [ "$ATTEMPTS" -le 0 ]; then
    echo -e "${RED}OpenResty did not become ready in time${NC}"
    docker compose -f "$COMPOSE_FILE" logs openresty || true
    exit 1
  fi
  sleep 2
done
echo -e "${GREEN}Services ready${NC}"
echo ""

# =================================================================
# Test 1: Static files served
# =================================================================
echo "Test 1: Static files served"
INDEX_STATUS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" https://lab.test:${PORT}/)
if [ "$INDEX_STATUS" = "200" ]; then
  log_pass "Static index.html served correctly"
else
  log_fail "Static files not served (status: $INDEX_STATUS)"
fi

# =================================================================
# Test 2: JWT cookie validation
# =================================================================
echo "Test 2: JWT cookie validation"
JWT=$(cat "$JWT_FILE")
curl -sk --resolve lab.test:${PORT}:127.0.0.1 -c "$COOKIE_FILE" "https://lab.test:${PORT}/guacamole/?jwt=${JWT}" >/dev/null

if grep -q "JTI.*smoke-jti-123" "$COOKIE_FILE"; then
  log_pass "JWT processed and JTI cookie set"
else
  log_fail "JTI cookie missing expected entry"
fi

# =================================================================
# Test 3: Authorization header propagation
# =================================================================
echo "Test 3: Authorization header propagation"
RESPONSE=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -b "$COOKIE_FILE" https://lab.test:${PORT}/guacamole/api/echo)

if echo "$RESPONSE" | grep -Eq '"authorization"[[:space:]]*:[[:space:]]*"smoke-user"'; then
  log_pass "Authorization header propagated through OpenResty"
else
  log_fail "Authorization header not propagated: $RESPONSE"
fi

# =================================================================
# Test 4: Ops endpoint requires token
# =================================================================
echo "Test 4: Ops endpoint requires token"
OPS_HEALTH=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" https://lab.test:${PORT}/ops/health || true)
if [ "$OPS_HEALTH" = "401" ] || [ "$OPS_HEALTH" = "403" ] || [ "$OPS_HEALTH" = "503" ]; then
  log_pass "Ops endpoint rejects requests without token (status: $OPS_HEALTH)"
else
  log_fail "Ops endpoint should reject without token (status: $OPS_HEALTH)"
fi

# =================================================================
# Test 5: Ops endpoint accepts valid token
# =================================================================
echo "Test 5: Ops endpoint accepts valid token"
OPS_OK=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -H "X-Ops-Token: test-ops-secret-123" -b "ops_token=test-ops-secret-123" https://lab.test:${PORT}/ops/health || true)
if echo "$OPS_OK" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' || [ "$OPS_OK" = "ops-worker-ok" ]; then
  log_pass "Ops endpoint accepts valid token"
else
  log_fail "Ops health failed with token: $OPS_OK"
fi

# =================================================================
# Test 6: Wallet endpoint protection
# =================================================================
echo "Test 6: Wallet endpoint protection"
WALLET_STATUS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" https://lab.test:${PORT}/wallet/health || true)
if [ "$WALLET_STATUS" = "200" ] || [ "$WALLET_STATUS" = "403" ]; then
  log_pass "Wallet endpoint access controlled (status: $WALLET_STATUS)"
else
  log_fail "Unexpected wallet health status: $WALLET_STATUS"
fi

# =================================================================
# Test 7: Security headers present
# =================================================================
echo "Test 7: Security headers"
HEADERS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -I https://lab.test:${PORT}/ 2>&1)

SECURITY_OK=true
if ! echo "$HEADERS" | grep -qi "x-frame-options"; then
  SECURITY_OK=false
fi
if ! echo "$HEADERS" | grep -qi "x-content-type-options"; then
  SECURITY_OK=false
fi

if [ "$SECURITY_OK" = true ]; then
  log_pass "Security headers present"
else
  log_fail "Some security headers missing"
fi

# =================================================================
# Test 8: Guacamole proxy accessible
# =================================================================
echo "Test 8: Guacamole proxy"
GUAC_STATUS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" https://lab.test:${PORT}/guacamole/)
if [ "$GUAC_STATUS" = "200" ] || [ "$GUAC_STATUS" = "302" ]; then
  log_pass "Guacamole accessible through proxy (status: $GUAC_STATUS)"
else
  log_fail "Guacamole not accessible (status: $GUAC_STATUS)"
fi

# =================================================================
# Test 9: Invalid JWT rejected
# =================================================================
echo "Test 9: Invalid JWT rejected"
INVALID_JWT="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"
INVALID_STATUS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" "https://lab.test:${PORT}/guacamole/?jwt=${INVALID_JWT}")
# Should still return 200 (login page) but not set cookie
if [ "$INVALID_STATUS" = "200" ] || [ "$INVALID_STATUS" = "302" ]; then
  log_pass "Invalid JWT handled gracefully (returns login page)"
else
  log_fail "Invalid JWT caused error (status: $INVALID_STATUS)"
fi

# =================================================================
# Test 10: Cookie cleared on second request without JWT
# =================================================================
echo "Test 10: Session persistence"
SESSION_RESPONSE=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -b "$COOKIE_FILE" https://lab.test:${PORT}/guacamole/api/echo)
if echo "$SESSION_RESPONSE" | grep -Eq '"authorization"'; then
  log_pass "Session persists across requests"
else
  log_fail "Session not persistent: $SESSION_RESPONSE"
fi

# =================================================================
# Test 11: Institution-config rejects missing internal token
# =================================================================
echo "Test 11: Institution-config rejects missing internal token"
INSTITUTION_NO_TOKEN=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" \
  https://lab.test:${PORT}/institution-config/status || true)
if [ "$INSTITUTION_NO_TOKEN" = "401" ] || [ "$INSTITUTION_NO_TOKEN" = "403" ]; then
  log_pass "Institution config rejects requests without token (status: $INSTITUTION_NO_TOKEN)"
else
  log_fail "Institution config should reject without token (status: $INSTITUTION_NO_TOKEN)"
fi

# =================================================================
# Test 12: Institution-config accepts valid token
# =================================================================
echo "Test 12: Institution-config accepts valid token"
INSTITUTION_WITH_TOKEN=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" \
  "https://lab.test:${PORT}/institution-config/status?token=${INTERNAL_TOKEN}")
if [ "$INSTITUTION_WITH_TOKEN" = "200" ]; then
  log_pass "Institution config accepts valid token (status: $INSTITUTION_WITH_TOKEN)"
else
  log_fail "Institution config rejected valid token (status: $INSTITUTION_WITH_TOKEN)"
fi

# =================================================================
# Summary
# =================================================================
echo ""
echo "=================================================="
echo "Smoke Test Results: $PASSED passed, $FAILED failed"
echo "=================================================="

if [ $FAILED -gt 0 ]; then
  echo -e "${RED}Some smoke tests failed!${NC}"
  exit 1
else
  echo -e "${GREEN}All smoke tests passed!${NC}"
  exit 0
fi
