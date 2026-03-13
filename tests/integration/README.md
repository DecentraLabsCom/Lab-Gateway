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

## FMU live stack verification

Use this when you want to validate the real `docker-compose.yml` stack instead of the mock integration stack.

PowerShell:

```powershell
# Validates the live gateway stack already running on localhost:8443
pwsh ./tests/integration/verify-fmu-live.ps1

# Full verification once you have a real FMU booking JWT
pwsh ./tests/integration/verify-fmu-live.ps1 `
  -BearerToken "<booking-jwt>" `
  -LabId "lab-1" `
  -ReservationKey "reservation-1"
```

What it checks:

- `docker compose` can reach the live stack
- `https://127.0.0.1:8443/fmu/health` is `UP`
- `fmuCount` is at least the expected value
- proxy runtime binaries exist inside `fmu-runner`
- `.fmu` files exist inside `fmu-data`
- forced expiry closes an attached realtime session with `reason=expired`
- `/auth/fmu/session-ticket/issue` and `/redeem` are exposed
- with `-BearerToken`, it also tests real `issue`, `redeem`, `proxy.fmu` download and parity between `describe` and generated `modelDescription.xml`

Helpers for local FMU proxy development:

```powershell
python .\tests\integration\new-fmu-dev-booking-token.py --access-key BouncingBall.fmu
```

Generates a dev FMU booking JWT signed with `Lab Gateway/certs/private_key.pem`.

```powershell
python .\tests\integration\simulate-proxy-fmu.py .\tests\integration\artifacts\fmu-proxy-lab-lab-1.fmu
```

Loads and simulates a downloaded `proxy.fmu` with `fmpy` on the Windows host to validate the native runtime.

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
