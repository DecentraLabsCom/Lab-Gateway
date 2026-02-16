#!/bin/bash
# =================================================================
# Run OpenResty Lua unit tests using Docker
# =================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENRESTY_DIR="$(dirname "$SCRIPT_DIR")"

echo "=================================================="
echo "OpenResty Lua Unit Tests"
echo "=================================================="
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not available. Please install Docker."
    exit 1
fi

# Create temporary Dockerfile
cat > "${OPENRESTY_DIR}/Dockerfile.test" << 'EOF'
FROM openresty/openresty:alpine

# Install luarocks and cjson
RUN apk add --no-cache luarocks5.1 lua5.1-dev gcc musl-dev && \
    luarocks-5.1 install lua-cjson

WORKDIR /app
EOF

cleanup() {
    rm -f "${OPENRESTY_DIR}/Dockerfile.test"
}
trap cleanup EXIT

echo "Building test container..."
docker build -t openresty-lua-tests -f "${OPENRESTY_DIR}/Dockerfile.test" "${OPENRESTY_DIR}" >/dev/null 2>&1

echo "Running tests..."
echo ""

# Run tests in container
docker run --rm \
    -v "$(dirname "$OPENRESTY_DIR"):/workspace:ro" \
    -w /workspace \
    openresty-lua-tests \
    luajit openresty/tests/run.lua

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\033[0;32mAll tests passed!\033[0m"
else
    echo -e "\033[0;31mSome tests failed!\033[0m"
fi

exit $EXIT_CODE
