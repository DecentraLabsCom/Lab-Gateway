#!/usr/bin/env bash
# =================================================================
# Integration Test Suite for DecentraLabs Gateway
# Tests rate limiting, health endpoints, and auth flows
# =================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.integration.yml"
CERTS_DIR="$SCRIPT_DIR/certs"
TEST_RESULTS=""
PASSED=0
FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function cleanup {
  echo -e "\n${YELLOW}Cleaning up...${NC}"
  docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
}

trap cleanup EXIT

# Generate test certificates if they don't exist
if [ ! -f "$CERTS_DIR/privkey.pem" ] || [ ! -f "$CERTS_DIR/fullchain.pem" ]; then
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
echo "DecentraLabs Gateway Integration Tests"
echo "=================================================="

# Start services
echo -e "\n${YELLOW}Starting services...${NC}"
docker compose -f "$COMPOSE_FILE" up --build -d

PORT=18443
BASE_URL="https://127.0.0.1:${PORT}"

echo "Waiting for services to be ready..."
if ! wait_for_service "${BASE_URL}/" 45; then
  echo -e "${RED}Services failed to start${NC}"
  docker compose -f "$COMPOSE_FILE" logs
  exit 1
fi
echo -e "${GREEN}Services ready${NC}\n"

# =================================================================
# Test 1: Health endpoint returns OK
# =================================================================
echo "Test 1: Health endpoint"
HEALTH_RESPONSE=$(curl -sk "${BASE_URL}/health" || echo "error")
if echo "$HEALTH_RESPONSE" | grep -q "ok\|UP\|healthy"; then
  log_pass "Health endpoint returns healthy status"
else
  log_fail "Health endpoint did not return healthy status: $HEALTH_RESPONSE"
fi

# =================================================================
# Test 2: Gateway health aggregates all services
# =================================================================
echo "Test 2: Gateway aggregated health"
GW_HEALTH=$(curl -sk "${BASE_URL}/gateway/health" || echo "error")
if echo "$GW_HEALTH" | grep -qE '"status"\s*:\s*"(ok|degraded)"'; then
  log_pass "Gateway health endpoint returns aggregated status"
else
  log_fail "Gateway health endpoint failed: $GW_HEALTH"
fi

# =================================================================
# Test 3: JWKS endpoint accessible
# =================================================================
echo "Test 3: JWKS endpoint"
JWKS_RESPONSE=$(curl -sk "${BASE_URL}/auth/jwks" || echo "error")
if echo "$JWKS_RESPONSE" | grep -q '"keys"'; then
  log_pass "JWKS endpoint returns keys"
else
  log_fail "JWKS endpoint did not return keys: $JWKS_RESPONSE"
fi

# =================================================================
# Test 4: OpenID Configuration endpoint
# =================================================================
echo "Test 4: OpenID Configuration"
OIDC_RESPONSE=$(curl -sk "${BASE_URL}/.well-known/openid-configuration" || echo "error")
if echo "$OIDC_RESPONSE" | grep -q '"issuer"'; then
  log_pass "OpenID Configuration endpoint returns issuer"
else
  log_fail "OpenID Configuration endpoint failed: $OIDC_RESPONSE"
fi

# =================================================================
# Test 5: Rate limiting - auth/message endpoint
# =================================================================
echo "Test 5: Rate limiting on auth endpoints"
RATE_LIMITED=false
for i in $(seq 1 20); do
  STATUS=$(curl -sk -o /dev/null -w "%{http_code}" "${BASE_URL}/auth/message")
  if [ "$STATUS" = "429" ]; then
    RATE_LIMITED=true
    break
  fi
done

if [ "$RATE_LIMITED" = true ]; then
  log_pass "Rate limiting kicks in after burst"
else
  log_fail "Rate limiting did not trigger after 20 requests (may need config adjustment)"
fi

# Wait a bit for rate limit to reset
sleep 5

# =================================================================
# Test 6: CORS headers present on auth endpoints
# =================================================================
echo "Test 6: CORS headers"
CORS_HEADERS=$(curl -sk -I -X OPTIONS "${BASE_URL}/auth/message" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" 2>&1)

if echo "$CORS_HEADERS" | grep -qi "access-control-allow"; then
  log_pass "CORS headers present on auth endpoints"
else
  log_fail "CORS headers missing on auth endpoints"
fi

# =================================================================
# Test 7: Guacamole proxy requires authentication
# =================================================================
echo "Test 7: Guacamole requires authentication"
GUAC_STATUS=$(curl -sk -o /dev/null -w "%{http_code}" "${BASE_URL}/guacamole/")
# Should return 200 (Guacamole login page) or redirect
if [ "$GUAC_STATUS" = "200" ] || [ "$GUAC_STATUS" = "302" ]; then
  log_pass "Guacamole endpoint accessible (login page)"
else
  log_fail "Guacamole endpoint returned unexpected status: $GUAC_STATUS"
fi

# =================================================================
# Test 8: Ops endpoint requires token
# =================================================================
echo "Test 8: Ops endpoint security"
OPS_NO_TOKEN=$(curl -sk -o /dev/null -w "%{http_code}" "${BASE_URL}/ops/health")
if [ "$OPS_NO_TOKEN" = "401" ] || [ "$OPS_NO_TOKEN" = "403" ] || [ "$OPS_NO_TOKEN" = "503" ]; then
  log_pass "Ops endpoint rejects requests without token"
else
  log_fail "Ops endpoint should reject without token, got: $OPS_NO_TOKEN"
fi

# =================================================================
# Test 9: Ops endpoint accepts valid token
# =================================================================
echo "Test 9: Ops endpoint with valid token"
OPS_WITH_TOKEN=$(curl -sk -H "X-Ops-Token: integration-test-secret" "${BASE_URL}/ops/health" || echo "error")
if echo "$OPS_WITH_TOKEN" | grep -q "ok\|status"; then
  log_pass "Ops endpoint accepts valid token"
else
  log_fail "Ops endpoint did not accept valid token: $OPS_WITH_TOKEN"
fi

# =================================================================
# Test 10: Static files served correctly
# =================================================================
echo "Test 10: Static files"
INDEX_STATUS=$(curl -sk -o /dev/null -w "%{http_code}" "${BASE_URL}/")
if [ "$INDEX_STATUS" = "200" ]; then
  log_pass "Static files served correctly"
else
  log_fail "Static files not served, status: $INDEX_STATUS"
fi

# =================================================================
# Test 11: HTTP to HTTPS redirect
# =================================================================
echo "Test 11: HTTP to HTTPS redirect"
HTTP_REDIRECT=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:18080/" 2>/dev/null || echo "000")
if [ "$HTTP_REDIRECT" = "301" ] || [ "$HTTP_REDIRECT" = "302" ]; then
  log_pass "HTTP redirects to HTTPS"
else
  log_fail "HTTP did not redirect, status: $HTTP_REDIRECT (might be expected if HTTP not exposed)"
fi

# =================================================================
# Test 12: Security headers present
# =================================================================
echo "Test 12: Security headers"
SEC_HEADERS=$(curl -sk -I "${BASE_URL}/" 2>&1)
SEC_PASS=true

if ! echo "$SEC_HEADERS" | grep -qi "strict-transport-security"; then
  echo "  Missing: Strict-Transport-Security"
  SEC_PASS=false
fi

if ! echo "$SEC_HEADERS" | grep -qi "x-frame-options"; then
  echo "  Missing: X-Frame-Options"
  SEC_PASS=false
fi

if ! echo "$SEC_HEADERS" | grep -qi "x-content-type-options"; then
  echo "  Missing: X-Content-Type-Options"
  SEC_PASS=false
fi

if [ "$SEC_PASS" = true ]; then
  log_pass "Security headers present"
else
  log_fail "Some security headers missing"
fi

# =================================================================
# Summary
# =================================================================
echo ""
echo "=================================================="
echo "Test Results"
echo "=================================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo "=================================================="

if [ $FAILED -gt 0 ]; then
  exit 1
fi

echo -e "\n${GREEN}All integration tests passed!${NC}"
