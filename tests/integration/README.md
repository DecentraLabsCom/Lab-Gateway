# Integration Tests

This directory contains integration tests for the DecentraLabs Gateway.

## Overview

The integration tests verify the correct behavior of the full gateway stack including:

- **Rate Limiting**: Verifies that public auth endpoints are rate-limited
- **Health Endpoints**: Tests aggregated health checks across all services
- **Authentication Flow**: Tests JWKS, OpenID Configuration, and token validation
- **Ops Worker Protection**: Verifies token-based access control
- **Security Headers**: Ensures all required security headers are present
- **HTTPS Redirect**: Verifies HTTP to HTTPS redirection

## Prerequisites

- Docker and Docker Compose
- Bash shell (Git Bash on Windows)
- curl

## Running Tests

```bash
# From the tests/integration directory
./run-integration.sh

# Or from the project root
./tests/integration/run-integration.sh
```

## Test Structure

```
tests/integration/
├── run-integration.sh           # Main test runner
├── docker-compose.integration.yml  # Test infrastructure
├── README.md                    # This file
├── certs/                       # Self-signed certificates for testing
│   └── generate-certs.sh       # Certificate generation script
└── mocks/                       # Mock services
    ├── blockchain-services/    # Mock auth service with rate limiting
    │   ├── Dockerfile
    │   └── server.py
    ├── guacamole/             # Mock Guacamole API
    │   ├── Dockerfile
    │   └── server.py
    └── ops-worker/            # Mock ops-worker service
        ├── Dockerfile
        └── server.py
```

## Test Cases

| # | Test | Description |
|---|------|-------------|
| 1 | Health endpoint | Verifies `/health` returns healthy status |
| 2 | Gateway aggregated health | Verifies `/gateway/health` aggregates all services |
| 3 | JWKS endpoint | Verifies `/auth/jwks` returns public keys |
| 4 | OpenID Configuration | Verifies `/.well-known/openid-configuration` |
| 5 | Rate limiting | Verifies rate limiting triggers on burst requests |
| 6 | CORS headers | Verifies CORS headers on auth endpoints |
| 7 | Guacamole access | Verifies Guacamole endpoint is accessible |
| 8 | Ops security (no token) | Verifies ops endpoint rejects unauthorized requests |
| 9 | Ops security (valid token) | Verifies ops endpoint accepts valid token |
| 10 | Static files | Verifies static files are served correctly |
| 11 | HTTP redirect | Verifies HTTP to HTTPS redirect |
| 12 | Security headers | Verifies HSTS, X-Frame-Options, etc. |

## Mock Services

### blockchain-services (Port 8080)
Simulates the authentication service with:
- Rate limiting (5 requests per 10 seconds per IP)
- JWT/JWKS generation
- OpenID Configuration
- Wallet authentication simulation

### guacamole (Port 8080)
Simulates Apache Guacamole API with:
- Connection listing
- Token-based authentication
- Session management

### ops-worker (Port 5001)
Simulates the lab station operations service with:
- Health endpoints
- Lab station management
- WoL/command simulation

## Environment Variables

The docker-compose.integration.yml uses these environment variables for OpenResty:

| Variable | Value | Description |
|----------|-------|-------------|
| `SERVER_NAME` | localhost | Server hostname |
| `HTTPS_PORT` | 18443 | HTTPS port for tests |
| `HTTP_PORT` | 18080 | HTTP port for tests |
| `OPS_SECRET` | integration-test-secret | Token for ops-worker access |

## Cleanup

Tests automatically clean up containers after completion. To manually clean up:

```bash
docker compose -f docker-compose.integration.yml down -v
```

## Troubleshooting

### Services fail to start
Check the logs:
```bash
docker compose -f docker-compose.integration.yml logs
```

### Certificate issues
Regenerate certificates:
```bash
rm -f certs/privkey.pem certs/fullchain.pem
./certs/generate-certs.sh
```

### Rate limiting not triggering
The mock blockchain-services uses a 5 req/10s rate limit. Ensure no other requests are being made during the test.
