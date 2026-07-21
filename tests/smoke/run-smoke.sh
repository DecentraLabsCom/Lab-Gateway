#!/usr/bin/env bash
# =================================================================
# Smoke Test Suite for DecentraLabs Gateway
# Quick validation of core functionality after deployment
# =================================================================
set -euo pipefail

COMPOSE_FILE="tests/smoke/docker-compose.smoke.yml"
COOKIE_FILE="tests/smoke/cookie.txt"
JWT_FILE="tests/smoke/jwt.txt"
INVALID_COOKIE_FILE="tests/smoke/invalid-cookie.txt"
INSTITUTION_COOKIE_FILE="tests/smoke/institution-cookie.txt"
REPLAY_COOKIE_FILE="tests/smoke/replay-cookie.txt"
PASSED=0
FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

function cleanup {
  docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
  rm -f "$JWT_FILE"
  rm -f "$COOKIE_FILE"
  rm -f "$INVALID_COOKIE_FILE"
  rm -f "$INSTITUTION_COOKIE_FILE"
  rm -f "$REPLAY_COOKIE_FILE"
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

if ! command -v node >/dev/null 2>&1; then
  echo -e "${RED}Node.js is required to generate the smoke JWT${NC}"
  exit 1
fi
node --test tests/smoke/check-websocket-upgrade.test.mjs
node "${JWT_FILE%/*}/generate_jwt.js"

echo -e "${YELLOW}Starting services...${NC}"
docker compose -f "$COMPOSE_FILE" up --build -d

PORT=18443
ACCESS_TOKEN="smoke-access-token"

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
# Test 2: one-time access-code exchange and cookie validation
# =================================================================
echo "Test 2: one-time access-code exchange"
ACCESS_CODE=smoke-access-code
curl -sk --resolve lab.test:${PORT}:127.0.0.1 -c "$COOKIE_FILE" -X POST --data-urlencode "access_code=${ACCESS_CODE}" https://lab.test:${PORT}/auth/access >/dev/null

if grep -q "JTI.*smoke-jti-123" "$COOKIE_FILE"; then
  log_pass "Access code redeemed and JTI cookie set"
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
# Test 3b: Guacamole token durability runs in a cosocket-compatible phase
# =================================================================
echo "Test 3b: Guacamole token durability"
GUAC_TOKEN_RESPONSE=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -b "$COOKIE_FILE" \
  -X POST -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=SmokeUser&password=unused" \
  https://lab.test:${PORT}/guacamole/api/tokens)
if echo "$GUAC_TOKEN_RESPONSE" | grep -Eq '"authToken"[[:space:]]*:[[:space:]]*"admin-token"'; then
  log_pass "Guacamole token is returned after durable revocation registration"
else
  log_fail "Guacamole token was not secured in a compatible phase: $GUAC_TOKEN_RESPONSE"
fi

# =================================================================
# Test 3c: reservation WebSocket observation runs before proxy upgrade
# =================================================================
echo "Test 3c: Reservation WebSocket observation"
WEBSOCKET_COOKIE=$(awk -F '\t' '
  /^#HttpOnly_/ { sub(/^#HttpOnly_/, "") }
  !/^#/ && NF >= 7 {
    printf "%s%s=%s", separator, $6, $7
    separator = "; "
  }
' "$COOKIE_FILE")
WEBSOCKET_STATUS=$(SMOKE_WEBSOCKET_COOKIE="$WEBSOCKET_COOKIE" \
  node tests/smoke/check-websocket-upgrade.mjs 127.0.0.1 "$PORT" lab.test)
if [ "$WEBSOCKET_STATUS" = "101" ]; then
  log_pass "Reservation WebSocket is observed durably before upgrade"
else
  log_fail "Reservation WebSocket upgrade failed (status: $WEBSOCKET_STATUS)"
fi

# =================================================================
# Test 4: Ops health works without token
# =================================================================
echo "Test 4: Ops health without token"
OPS_HEALTH=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" https://lab.test:${PORT}/ops/health || true)
if [ "$OPS_HEALTH" = "200" ] || [ "$OPS_HEALTH" = "503" ]; then
  log_pass "Ops health works without token (status: $OPS_HEALTH)"
else
  log_fail "Ops health should not require token (status: $OPS_HEALTH)"
fi

# =================================================================
# Test 5: Ops API requires token and accepts valid token
# =================================================================
echo "Test 5: Ops API token protection"
OPS_API_NO_TOKEN=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" https://lab.test:${PORT}/ops/api/hosts || true)
OPS_OK=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" -H "X-Lab-Manager-Token: test-ops-secret-123" -b "lab_manager_token=test-ops-secret-123" https://lab.test:${PORT}/ops/api/hosts || true)
if { [ "$OPS_API_NO_TOKEN" = "401" ] || [ "$OPS_API_NO_TOKEN" = "403" ]; } \
  && [ "$OPS_OK" != "401" ] && [ "$OPS_OK" != "403" ]; then
  log_pass "Ops API requires token and accepts valid token"
else
  log_fail "Ops API token behavior mismatch: no-token=$OPS_API_NO_TOKEN with-token=$OPS_OK"
fi

# =================================================================
# Test 6: Ops endpoint rejects invalid token
# =================================================================
echo "Test 6: Ops endpoint rejects invalid token"
OPS_BAD_TOKEN=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" \
  -H "X-Lab-Manager-Token: wrong-token" \
  https://lab.test:${PORT}/ops/api/hosts || true)
if [ "$OPS_BAD_TOKEN" = "401" ] || [ "$OPS_BAD_TOKEN" = "403" ]; then
  log_pass "Ops endpoint rejects invalid token (status: $OPS_BAD_TOKEN)"
else
  log_fail "Ops endpoint should reject invalid token (status: $OPS_BAD_TOKEN)"
fi

# =================================================================
# Test 7: Wallet endpoint protection
# =================================================================
echo "Test 7: Wallet endpoint protection"
WALLET_STATUS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" https://lab.test:${PORT}/wallet/health || true)
if [ "$WALLET_STATUS" = "200" ]; then
  log_pass "Wallet health works without token (status: $WALLET_STATUS)"
else
  log_fail "Wallet health should not require token (status: $WALLET_STATUS)"
fi

# =================================================================
# Test 8: Security headers present
# =================================================================
echo "Test 8: Security headers"
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
# Test 9: Guacamole proxy accessible
# =================================================================
echo "Test 9: Guacamole proxy"
GUAC_STATUS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" https://lab.test:${PORT}/guacamole/)
if [ "$GUAC_STATUS" = "200" ] || [ "$GUAC_STATUS" = "302" ]; then
  log_pass "Guacamole accessible through proxy (status: $GUAC_STATUS)"
else
  log_fail "Guacamole not accessible (status: $GUAC_STATUS)"
fi

# =================================================================
# Test 10: Invalid access code rejected
# =================================================================
echo "Test 10: Invalid access code rejected"
rm -f "$INVALID_COOKIE_FILE"
INVALID_STATUS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -c "$INVALID_COOKIE_FILE" -o /dev/null -w "%{http_code}" -X POST --data-urlencode 'access_code=invalid-one-time-code' https://lab.test:${PORT}/auth/access)
if [ "$INVALID_STATUS" = "401" ] && ! grep -q "JTI" "$INVALID_COOKIE_FILE" 2>/dev/null; then
  log_pass "Invalid access code is handled gracefully without creating session cookies"
else
  log_fail "Invalid access code caused error (status: $INVALID_STATUS)"
fi

# =================================================================
# Test 11: Cookie cleared on second request without JWT
# =================================================================
echo "Test 11: Session persistence"
SESSION_RESPONSE=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -b "$COOKIE_FILE" https://lab.test:${PORT}/guacamole/api/echo)
if echo "$SESSION_RESPONSE" | grep -Eq '"authorization"'; then
  log_pass "Session persists across requests"
else
  log_fail "Session not persistent: $SESSION_RESPONSE"
fi

# =================================================================
# Test 12: Institution-config rejects missing access token for external clients
# =================================================================
echo "Test 12: Institution-config rejects missing access token for external clients"
INSTITUTION_EXTERNAL=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" \
  -H "X-Forwarded-For: 203.0.113.5" \
  https://lab.test:${PORT}/institution-config/status || true)
if [ "$INSTITUTION_EXTERNAL" = "401" ] || [ "$INSTITUTION_EXTERNAL" = "403" ]; then
  log_pass "Institution config rejects requests without token from external IP (status: $INSTITUTION_EXTERNAL)"
else
  log_fail "Institution config should reject external requests without token (status: $INSTITUTION_EXTERNAL)"
fi

# =================================================================
# Test 13: Institution-config rejects query-string token
# =================================================================
echo "Test 13: Institution-config rejects query-string token"
INSTITUTION_BAD_TOKEN=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" \
  "https://lab.test:${PORT}/institution-config/status?token=wrong-token")
if [ "$INSTITUTION_BAD_TOKEN" = "400" ]; then
  log_pass "Institution config rejects query-string token (status: $INSTITUTION_BAD_TOKEN)"
else
  log_fail "Institution config should reject query-string token (status: $INSTITUTION_BAD_TOKEN)"
fi

# =================================================================
# Test 14: Institution-config accepts valid POST login and cookie
# =================================================================
echo "Test 14: Institution-config accepts valid POST login and cookie"
rm -f "$INSTITUTION_COOKIE_FILE"
INSTITUTION_LOGIN_STATUS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 \
  -c "$INSTITUTION_COOKIE_FILE" -o /dev/null -w "%{http_code}" \
  -X POST --data-urlencode "token=${ACCESS_TOKEN}" \
  "https://lab.test:${PORT}/institution-config/login")
INSTITUTION_WITH_TOKEN=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 \
  -b "$INSTITUTION_COOKIE_FILE" -o /dev/null -w "%{http_code}" \
  "https://lab.test:${PORT}/institution-config/status")
if [ "$INSTITUTION_LOGIN_STATUS" = "204" ] && [ "$INSTITUTION_WITH_TOKEN" = "200" ]; then
  log_pass "Institution config accepts POST login and session cookie"
else
  log_fail "Institution config login/session failed: login=$INSTITUTION_LOGIN_STATUS status=$INSTITUTION_WITH_TOKEN"
fi

# =================================================================
# Test 15: Institution-config bootstrap redirects to the secure login page
# =================================================================
echo "Test 15: Institution-config bootstrap redirect"
INSTITUTION_BOOTSTRAP_HEADERS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -D - -o /dev/null \
  "https://lab.test:${PORT}/institution-config")
if echo "$INSTITUTION_BOOTSTRAP_HEADERS" | grep -Eq "^HTTP/.* 302" \
  && echo "$INSTITUTION_BOOTSTRAP_HEADERS" | grep -Eqi "^location: /admin-login.html\\?scope=billing"; then
  log_pass "Institution config redirects to secure login page"
else
  log_fail "Institution config bootstrap redirect mismatch: $INSTITUTION_BOOTSTRAP_HEADERS"
fi

# =================================================================
# Test 16: Lab-manager rejects external client forwarded through private proxy without token
# =================================================================
echo "Test 16: Lab-manager rejects forwarded external client without token"
LAB_MANAGER_EXTERNAL=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" \
  -H "X-Forwarded-For: 203.0.113.5" \
  https://lab.test:${PORT}/lab-manager/ || true)
if [ "$LAB_MANAGER_EXTERNAL" = "401" ]; then
  log_pass "Lab-manager rejects forwarded external client without token"
else
  log_fail "Lab-manager should reject forwarded external client (status: $LAB_MANAGER_EXTERNAL)"
fi

# =================================================================
# Test 17: Lab-manager bootstrap redirects to the secure login page
# =================================================================
echo "Test 17: Lab-manager bootstrap redirect"
LAB_MANAGER_BOOTSTRAP_HEADERS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -D - -o /dev/null \
  -H "Accept: text/html" \
  "https://lab.test:${PORT}/lab-manager")
if echo "$LAB_MANAGER_BOOTSTRAP_HEADERS" | grep -Eq "^HTTP/.* 302" \
  && echo "$LAB_MANAGER_BOOTSTRAP_HEADERS" | grep -Eqi "^location: /\\?auth=lab-manager&next=/lab-manager/"; then
  log_pass "Lab-manager redirects to secure login page"
else
  log_fail "Lab-manager bootstrap redirect mismatch: $LAB_MANAGER_BOOTSTRAP_HEADERS"
fi

# =================================================================
# Test 18: AAS admin requires token even on local/private requests
# =================================================================
echo "Test 18: AAS admin requires token even on local/private requests"
AAS_ADMIN_NO_TOKEN=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" \
  -X POST https://lab.test:${PORT}/aas-admin/fmu/test.fmu/sync || true)
if [ "$AAS_ADMIN_NO_TOKEN" = "401" ] || [ "$AAS_ADMIN_NO_TOKEN" = "503" ]; then
  log_pass "AAS admin rejects local/private request without token (status: $AAS_ADMIN_NO_TOKEN)"
else
  log_fail "AAS admin should reject local/private request without token (status: $AAS_ADMIN_NO_TOKEN)"
fi

# =================================================================
# Test 19: AAS admin accepts valid lab manager token
# =================================================================
echo "Test 19: AAS admin accepts valid lab manager token"
AAS_ADMIN_WITH_TOKEN=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -o /dev/null -w "%{http_code}" \
  -X POST -H "X-Lab-Manager-Token: test-ops-secret-123" \
  https://lab.test:${PORT}/aas-admin/fmu/test.fmu/sync || true)
if [ "$AAS_ADMIN_WITH_TOKEN" = "200" ]; then
  log_pass "AAS admin accepts valid lab manager token"
else
  log_fail "AAS admin should accept valid lab manager token (status: $AAS_ADMIN_WITH_TOKEN)"
fi

# =================================================================
# Test 20: Access codes cannot be redeemed twice
# =================================================================
echo "Test 20: Access code replay rejected"
rm -f "$REPLAY_COOKIE_FILE"
REPLAY_STATUS=$(curl -sk --resolve lab.test:${PORT}:127.0.0.1 -c "$REPLAY_COOKIE_FILE" -o /dev/null -w "%{http_code}" \
  -X POST --data-urlencode "access_code=${ACCESS_CODE}" https://lab.test:${PORT}/auth/access)
if [ "$REPLAY_STATUS" = "401" ] && ! grep -q "JTI" "$REPLAY_COOKIE_FILE" 2>/dev/null; then
  log_pass "Redeeming an access code a second time is rejected without creating a session cookie"
else
  log_fail "Access-code replay was not rejected safely (status: $REPLAY_STATUS)"
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
