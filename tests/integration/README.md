# Integration Tests

This suite validates OpenResty routing and security behavior against mock services.

## Real Compose resilience gate

Use this gate to exercise the database-dependent services and the real edge in
the root Compose stack. It starts MySQL, the embedded blockchain-services,
Guacamole, guacd, Ops Worker, OpenResty, and the production FMU Runner. In
addition to readiness it restarts OpenResty, checks that the edge recovers,
inserts a real Guacamole history record and verifies that Ops Worker creates a
durable session observation, and drives the production FMU queue past capacity
to verify newest-event retention and drop accounting. It removes only the
resources belonging to its temporary Compose project when it finishes.

Prerequisites:

- a configured root `.env`
- a configured `blockchain-services/.env`
- Docker images/build dependencies available locally

```bash
bash ./tests/integration/run-compose-stack-integration.sh
```

Set `COMPOSE_STACK_TEST_TIMEOUT_SECONDS` to change the default 10-minute
resilience timeout. CI uses
`tests/integration/prepare-real-compose-ci.sh` to create an isolated env,
backend env, and Compose secret override; it never needs the developer's
production `.env` or `secrets/` directory.

## What is covered

- `/health` and `/gateway/health`
- `/auth/jwks` and OIDC discovery (`/.well-known/openid-configuration`) through
  the mock backend routing surface
- Auth endpoint rate limiting behavior (mocked backend)
- CORS behavior on auth paths
- `/ops` token protection
- Static files and HTTP->HTTPS redirect
- Security headers
- Vertical anonymous demo flow: Marketplace publication/sanitation/catalogue,
  `/auth/demo`, `DEMO_JTI`, Guacamole token/session scoping, Ops lifecycle and
  concurrent-slot rejection

The integration suite validates the Gateway routing surface with a mock backend;
the canonical embedded backend serves both `/auth/jwks` and
`/.well-known/openid-configuration` in provider mode. See the backend
authentication guide for the production authentication boundary.

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

## Full/Lite access-plane gate

Run the dedicated Full/Lite scenario when changing issuer trust, access-code
redemption, Guacamole provisioning, observer credentials, or the `/auth/**`
mode boundary:

```bash
./tests/integration/run-full-lite-access-integration.sh
```

This gate starts two real OpenResty edges. Its control-plane fixture signs
RS256 credentials with a generated RSA key and models the contract states
`CONFIRMED` and `ACCESS_AUTHORIZED`; the access-code endpoint remains closed
until the latter. It then checks remote Lite key synchronization, a JWT issued
by the remote authority, the server-side access-code prepare/commit flow,
reservation-scoped Guacamole sessions, the explicit remote provisioner route,
the scoped observer JWT, and the Full/Lite `/auth/**` distinction.

The fixture is intentionally isolated from production secrets and databases.
The canonical on-chain/backend semantics remain covered by the Foundry and
Spring tests; this Docker gate covers the cross-service edge protocol that
those tests cannot exercise.

The gate also checks redemption lease expiry, concurrent access-code fencing,
durable FMU mappings across an OpenResty restart, and Station outage followed
by reconnection. Those cases use deterministic control-plane/Station
fixtures, while the real Compose gate above covers the persistence and runtime
boundaries that require MySQL, Guacamole, and the production worker.

The Docker gate uses a deterministic Marketplace authority and controlled
Guacamole/Ops/Station mocks. It is the repeatable cross-container contract
test; it does not replace the live hardware gate below.

## Live demo browser gate

The Marketplace repository contains an opt-in Cypress test for a deployed
Marketplace and Gateway. It never fabricates catalogue or handoff responses;
the configured lab must already be published, listed, physical, HTTPS-backed,
and connected to a controlled Guacamole/Lab Station setup.

```powershell
$env:CYPRESS_DEMO_LIVE = "true"
$env:CYPRESS_BASE_URL = "https://marketplace.example"
$env:CYPRESS_DEMO_GATEWAY_URL = "https://gateway.example"
$env:CYPRESS_DEMO_LAB_ID = "42"
$env:CYPRESS_DEMO_CONNECTION_ID = "7"
cd ..\..\Marketplace
npm run test:e2e:demo
```

The gate verifies the real Marketplace catalogue, Gateway readiness, HTTPS
handoff, Secure/HttpOnly `DEMO_JTI`, Guacamole token exchange, session identity
and the single configured connection. It is deliberately disabled unless
`CYPRESS_DEMO_LIVE=true` and all endpoints/IDs are supplied.

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

To validate the realtime Gateway stream directly from a downloaded proxy (without hiding the WebSocket events behind an FMI tool), run:

```powershell
python .\tests\integration\probe_proxy_stream.py "$env:USERPROFILE\Downloads\fmu-proxy-lab-id.fmu"
```

The probe validates `session.create`, `model.describe`, `sim.initialize`,
`sim.subscribeOutputs`, `sim.start`, several monotonic `sim.outputs` events,
`sim.pause`, and `session.terminate`. Use `--insecure` only against a local
gateway with a self-signed certificate. A proxy's session ticket is short-lived;
download a fresh proxy when the probe reports an expired ticket.

OpenModelica / OMSimulator validation:

```powershell
pwsh .\tests\integration\verify-openmodelica-omsimulator.ps1
```

What it checks:

- downloads fresh `proxy.fmu` artifacts for `Feedthrough.fmu`
- runs a composite OMSimulator model with:
  - one local `Feedthrough.fmu`
  - one remote `proxy.fmu`
  - a real connection from the local output to the remote input
- exports the composed model to an `.ssp` archive
- runs a second stepwise OMSimulator session using `oms_stepUntil(...)` and `oms_setReal(...)`
- verifies that the remote proxy output follows host-side input changes

Notes:

- this is the relevant OpenModelica compatibility path for the proxy today, not `omc importFMU(...)`
- the exported `.ssp` can be opened from OMEdit as a composite/OMSimulator model
- the embedded `proxy.fmu` remains reservation-bound and time-limited, so regenerate it when the ticket expires

## Files

```text
tests/integration/
|- run-integration.sh
|- run-compose-stack-integration.sh
|- prepare-real-compose-ci.sh
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
