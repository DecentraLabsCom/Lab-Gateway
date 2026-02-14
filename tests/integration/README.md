# Integration Tests

This suite validates OpenResty routing and security behavior against mock services.

## What is covered

- `/health` and `/gateway/health`
- OIDC endpoints (`/auth/jwks`, `/.well-known/openid-configuration`)
- Auth endpoint rate limiting behavior (mocked backend)
- CORS behavior on auth paths
- `/ops` token protection
- Static files and HTTP->HTTPS redirect
- Security headers

## Prerequisites

- Docker + Docker Compose plugin
- Bash (Git Bash on Windows)
- `curl`

## Run

```bash
# From repo root
./tests/integration/run-integration.sh

# Or inside tests/integration
./run-integration.sh
```

## Files

```text
tests/integration/
|- run-integration.sh
|- docker-compose.integration.yml
|- certs/generate-certs.sh
`- mocks/
   |- blockchain-services/
   |- guacamole/
   `- ops-worker/
```

## Important ports (test stack)

- OpenResty HTTPS: `18443`
- OpenResty HTTP: `18080`
- Mock ops-worker: `5001` (internal)

## Cleanup

The script cleans up automatically. Manual cleanup:

```bash
docker compose -f tests/integration/docker-compose.integration.yml down -v
```

## Troubleshooting

```bash
docker compose -f tests/integration/docker-compose.integration.yml logs
```
