# Release gate E2E

This directory contains the executable part of the release gate. It uses real
MySQL, Redis with AOF persistence, and Anvil. The Redis REST bridge is only a
protocol adapter: Marketplace still exercises Redis commands and Lua `EVAL`
against the real Redis process.

## Infrastructure smoke gate

From PowerShell:

```powershell
pwsh .\tests\e2e\run-release-gate.ps1
```

The script starts an isolated Compose project, checks health, exercises Redis
atomicity, restarts Redis, verifies that the value survives, writes a scoped
InnoDB marker, restarts MySQL, and checks Anvil RPC/deployed bytecode when
`CONTRACT_ADDRESS` is supplied. Use
`-KeepStack` while debugging.

The local Docker daemon must be running. The default Compose file deliberately
does not invent Marketplace, provider credentials, an IdP, or a Windows
Station; those are supplied by the deployment under test.

## Application and fault scenarios

For a production gate, configure the application endpoints and require them:

```powershell
$env:RELEASE_GATE_REQUIRE_APPLICATIONS = "1"
$env:RELEASE_GATE_APPLICATIONS = '{"marketplace":"https://marketplace.test","consumer":"http://127.0.0.1:8081","provider":"http://127.0.0.1:8082","gateway":"https://127.0.0.1:8443"}'
python .\tests\e2e\release_gate.py
```

Set `COMPOSE_FILE` and `COMPOSE_PROJECT_NAME` to the actual Compose project if
the scenario file must restart backend replicas. A scenario file must give
each request a name, URL and expected status; `restartBefore` and
`restartAfter` create deliberate durable-boundary restarts. The example file
is a template only because the real URLs and authentication payloads are
deployment-specific.

Marketplace's browser-level checks are in
`Marketplace/cypress/e2e/release-gate.cy.js` and run with:

```powershell
$env:CYPRESS_RELEASE_GATE = "true"
npm run test:e2e:release-gate
```

## Existing release-gate coverage

The gate composes with the existing suites rather than duplicating their
fixtures:

- Solidity: exact TTL/deadline boundaries, confirmation window, 128 lots,
  source-lot refunds/rounding, legacy allocation cursor, and lab deletion
  invariants are under `Smart-Contracts/test/`.
- Backend: real-MySQL replica races, whitelist/multiple-Assertion SAML,
  WebAuthn UV policy, check-in/redeem generations, SessionStarted nonce
  ownership, settlement durability, and deployment verification are under
  `blockchain-services/src/test/`.
- Gateway/Marketplace: real HTTP readiness, catalogue, auth discovery and
  Redis atomic hand-off are covered by the runners above.

The remaining cases require real external actors and must be supplied through
the scenario file or a deployment-specific adapter: an actual SAML IdP,
browser WebAuthn authenticator, Guacamole/Station check-in, provider outage
until on-chain TTL, and a two-replica FMU capacity run. The gate fails when a
configured scenario does not produce its declared outcome; it never treats an
unconfigured external actor as passing coverage.
