# FMI/FMU Support

This document covers the Gateway-facing FMU product: provider setup, reservation-bound access,
proxy delivery, and browser-app connection grants. The [FMU Executor README](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md)
owns the execution runtime, private API and WebSocket message contract, validation and isolation
behavior, limits, and FMI conformance baseline.

## Contents

- [What DecentraLabs provides](#what-decentralabs-provides)
- [Architecture and trust boundaries](#architecture-and-trust-boundaries)
- [Provider guide](#provider-guide)
- [User guide](#user-guide)
- [Jobs, batches, and history](#6-jobs-batches-and-history)
- [Complete provider web apps](#complete-provider-web-apps)
- [Gateway-to-Station contract](#gateway-to-station-contract)
- [Security and operational rules](#security-and-operational-rules)
- [Relationship to adjacent standards](#relationship-to-adjacent-standards)
- [Detailed implementation references](#detailed-implementation-references)
- [Acceptance checklist](#acceptance-checklist)

## What DecentraLabs provides

DecentraLabs exposes a protected FMU as a reservation-scoped remote simulation:

- In production, the provider's real `.fmu` remains on Lab Station and is never delivered to the
  user. Local development uses separate Executor containers and local fixtures.
- Marketplace does not upload the real model. The provider provisions it on the execution station
  and publishes an `accessKey` reference.
- Marketplace automatically downloads the generated `proxy.fmu` when a user enters a reserved FMU
  lab. A native FMI client can also request it directly, import it, and run the model through the
  Gateway.
- A short-lived, reservation-bound session ticket binds the real-time session to the user, lab and
  reservation.
- Reservation windows, availability rules, terms and existing lab metadata apply to FMU resources in
  the same way as to physical laboratories.

The current product focuses on FMI 2.x and FMI 3.x Co-Simulation. See the Executor's
[FMI conformance baseline](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md#fmi-conformance-baseline)
for the validated execution subset; the native proxy's platform and tool validation is tracked in
[proxy runtime source](../fmu-proxy-runtime-src/README.md).

FMI identifies its major and minor version in modelDescription.xml (for example, 2.0 or 3.0), not
the standard patch release. See the [official FMI
releases](https://github.com/modelica/fmi-standard/releases) and the [FMI 3.0.2
specification](https://fmi-standard.org/docs/3.0.2/).

## Two perspectives at a glance

| Provider | User |
| --- | --- |
| Installs and validates the real FMU on Lab Station. | Reserves the FMU in Marketplace. |
| Publishes `resourceType=fmu`, `accessURI` and the Station `accessKey`. | Downloads a reservation-scoped `proxy.fmu`. |
| Configures the Gateway and Station execution path. | Imports the proxy into an FMI-compatible tool. |
| Controls the exposed FMI interface and optional name obfuscation. | Uses standard FMI calls; no local agent is required. |
| Keeps model IP and runtime data under provider control. | Never receives the real model binary. |

## Architecture and trust boundaries

The system separates control, delivery and execution:

~~~mermaid
flowchart LR
    Tool["User FMI tool"] --> Proxy["reservation-scoped proxy.fmu"]
    Proxy <-- "WSS" --> Gateway["Lab Gateway\nOpenResty + FMU facade"]
    Gateway <-- "REST / auth" --> Services["Marketplace + blockchain-services"]
    Gateway <-- "private REST / WS" --> Station["Lab Station\nfmu-executor"]
    Station --> Model["Provider's real .fmu"]
~~~

### Control plane

Marketplace and `blockchain-services` handle listings, reservations, availability, authorization,
session-ticket issuance and audit-related decisions.

### Delivery plane

The Gateway obtains the model description from the real FMU and creates the proxy archive. The proxy
contains only:

- `modelDescription.xml` describing the exposed FMI interface;
- proxy runtime binaries for supported platforms; and
- `resources/config.json` with reservation-scoped connection data.

It does not contain the provider's model binaries or model assets.

### Execution plane

Lab Station stores, loads and executes the real FMU. In production, the Gateway must not require the
real FMU in its own filesystem.

The Gateway does not execute FMUs in-process. Its `fmu-local-dev` profile points the facade at the
shared FMU Executor container through the same private HTTP/WSS contract used by Lab Station.
Production uses `station` mode to forward through the private Station APIs. When no Executor is
configured, the local backend is limited to listing and reading metadata; run, stream and realtime
requests require a remote Executor.

## Provider guide

### 1. Provision and validate the FMU

Place the real model in the Station FMU store, using the layout and `FMU_ROOT` rules in the
Executor's [FMU provisioning guide](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md#fmu-provisioning):

Before publication, validate it through the Station's private Executor API. Its
[internal API](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md#internal-api)
and [validation results](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md#admission-expiry-isolation-and-execution-evidence)
document the validation fields, optional isolated probe, quarantine operations, and limits of what
a passing probe establishes. These private endpoints are not called by Marketplace users. Gateway
public descriptions use the reduced `publicOnly=true` view where appropriate; the Executor still
validates and parses the full model description.

### 2. Publish the resource

Register the resource in Marketplace with:

~~~text
resourceType = fmu
accessURI    = <public provider Gateway>
accessKey    = <Station FMU identifier>
~~~

The `accessKey` is an operational/versioned reference. It is not a substitute for the stable
resource identity used by Marketplace and the reservation system.

### 3. Configure the execution backend

For the production Station path, configure the Gateway with the Station internal URL, internal
session token and:

~~~text
FMU_BACKEND_MODE=station
FMU_JWT_AUDIENCE=https://<public-gateway-origin>/fmu
~~~

The Station channel uses one Gateway-owned internal token, not a browser credential or a
certificate. `setup.sh`/`setup.bat` generates `FMU_STATION_INTERNAL_TOKEN` and synchronizes it as a
Compose secret for `fmu-runner`, the embedded backend and `ops-worker`. Register the Station in the
Gateway host inventory and set `FMU_STATION_BASE_URL` to its executor URL
(`http://<station-address>:8091` by default). If the URL hostname is not the inventory address, set
`FMU_STATUS_STATION_HOST` to the registered host name.

From Lab Manager > Lab Station Ops, the configured Station row exposes a `Link FMU token` action.
The operation follows the Station management contract: Windows v2 over WinRM writes the token to the
machine-level `FMU_INTERNAL_TOKEN` variable and starts or restarts `LabStation\BackgroundService`;
Linux v3 over SSH stores it in the root-owned
`/etc/decentralabs/lab-station/secrets/fmu-internal-token.env` file with mode `0600`, then starts or
restarts `decentralabs-labstation-fmu`. Releasing the token removes the Windows machine variable and
restarts the background task; on Linux it removes the secret file and stops the FMU service. Once
linked, the row changes to `Release FMU token` and other Station rows remain disabled. The token is
never returned to the browser. A Gateway cannot link a second host: the selected host must resolve
to the single Station represented by `FMU_STATION_BASE_URL`/`FMU_STATUS_STATION_HOST`.

The panel status is authenticated end-to-end through `GET /internal/fmu/capacity`; the
unauthenticated `/internal/health` response alone is not considered proof that the Gateway and
Station share a token.

The Station is the single operational capacity authority. Set its `FMU_MAX_SESSIONS` value to the
effective execution limit; the provider backend reads `GET /internal/fmu/capacity` before FMU
publication and provider confirmation, and rejects metadata without a positive off-chain
`maxConcurrentUsers` declaration or whose declaration exceeds that limit. The contract stores
`resourceType`; `maxConcurrentUsers` remains provider metadata and is revalidated inside the
provider confirmation lock. A capacity read failure leaves a pending reservation retryable.

For isolated local development/tests, start the `fmu-local-dev` Compose profile. The Gateway facade
delegates batch, stream and realtime execution to the versioned image selected by
`FMU_EXECUTOR_IMAGE`; the [configuration reference](reference/configuration.md) documents its
default. No separate Executor source checkout is required. The Executor shares `./fmu-data` with
the Gateway facade and is reachable only over the internal local edge. It receives a dedicated
internal token; the Gateway also receives the session-observer credential required for authenticated
ticket redemption and durable session observation. The public booking JWT is not the sole
protection of the internal channel.

The Gateway uses FMPy to read model descriptions for AAS metadata and proxy generation; model
loading and simulation are handled by the Executor. Lab Stations package a released Executor
snapshot in their platform runtime.

JWT key retrieval is independent of the FMU execution backend. In Full mode the runner uses
`http://blockchain-services:8080/auth/jwks`; in Lite mode it uses the external issuer's JWKS
endpoint. `AUTH_JWKS_URL` may explicitly override that selection, but it is subject to the same
HTTPS requirement; HTTP is only accepted for loopback/private hosts used by local Compose
networking. The local profile reaches the Full-mode endpoint through the dedicated internal
`fmu_auth` network.

### 4. Manage interface disclosure

When an AAS is linked, its IDTA 01004 Part 4 SimulationAccessControl rules can restrict variable
reads and writes. The Gateway enforces these rules before forwarding requests and filters returned
values. An AAS without a compatible policy uses FMI-derived defaults; an unreadable or invalid
linked AAS fails closed. These rules protect simulation operations and values, not static interface
metadata that may already be public. See [AAS support](aas-support.md#fmi-variable-access-policy)
for the mapping and enforcement model. Private aliases can reduce semantic leakage but are not an
authorization control.

### 5. Preserve common resource metadata

FMU listings use the same functional metadata as physical labs:

- images and documentation;
- terms and conditions;
- availability and unavailability windows; and
- allowed reservation and usage timing.

These fields are used for catalogue display, reservation validation, execution-window enforcement
and auditability.

## User guide

### 1. Reserve the FMU

Create a reservation in Marketplace. The reservation must be active and its availability and time
window must be valid before a proxy can be downloaded or a real-time session can be created.

### 2. Automatic download or direct proxy request

Marketplace downloads the reservation-scoped artifact automatically when a user enters the reserved
lab. A native FMI client can request the artifact directly:

~~~text
GET /fmu/api/v1/fmu/proxy/{labId}?reservationKey=<reservation-key>
~~~

The request requires an authenticated session and authorization over the reservation. The response
is an `application/octet-stream` FMU archive. The Gateway may also return:

- `X-Proxy-Artifact-Sha256`, the SHA-256 hash of the generated artifact; and
- `X-Proxy-Artifact-Signature`, an optional `hmac-sha256=<hex>` signature when the provider
  configured artifact signing.

When downloading directly, verify the hash and the signature when present before importing the
proxy. If its embedded ticket expires or the reservation is cancelled, request a fresh artifact.
Ticket redemption rechecks the current on-chain reservation state.

### 3. Import and run it in an FMI tool

Import `proxy.fmu` as a normal Co-Simulation FMU. The proxy opens a secure WebSocket to the provider
Gateway, exchanges the reservation-bound ticket and maps FMI calls to the remote real-time API. No
local DecentraLabs agent is needed.

The externally advertised Gateway facade is:

~~~text
WSS /fmu/api/v1/fmu/sessions
~~~

Internal `fmu-runner` paths may appear as `/api/v1/...` behind the OpenResty route.

### 4. Session lifecycle

The proxy forwards FMI lifecycle and variable operations through the Gateway's authenticated
WebSocket facade. Gateway ticket redemption binds the session to the user, lab and reservation;
reservation expiry closes it. In Station mode, an unexpected internal disconnect can be resumed
with `session.attach` during the configured grace window. The Executor README owns the message
types, payloads, step behavior, and reconnect contract in its
[Realtime WebSocket protocol](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md#realtime-websocket-protocol).

A session ticket is bound to the user, lab and reservation. Its default TTL is 120 seconds and its
configured maximum is 300 seconds. Tickets remain reusable for reconnects while valid; redemption
rechecks the current on-chain reservation and ticket bindings. Other expected errors include
`SESSION_TICKET_INVALID`, `SESSION_TICKET_EXPIRED`, `RESERVATION_NOT_ACTIVE`, `SESSION_EXPIRED`,
`SESSION_TICKET_RESERVATION_STATE_UNAVAILABLE`, `RATE_LIMITED` and `INTERNAL_ERROR`.

### 5. Simulation time and streaming

Generated proxies use `external` time mode by default because the importing FMI tool owns the
`doStep` sequence. Providers can select another proxy mode with `FMU_PROXY_TIME_MODE`
(`simtime`, `realtime` or `external`); `FMU_PROXY_PLAYBACK_SPEED` sets the realtime multiplier
(default `1`, range `0.1` to `100`). These settings control pacing, not the FMU's simulation
results. Step negotiation, tunable FMI 2/3 parameters, scheduled writes, event handling, output
subscriptions and rate limits are part of the Executor's
[runtime contract](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md#runtime-capabilities).

### 6. Jobs, batches, and history

Clients can submit one asynchronous simulation or a small batch of parameter scenarios through the
reservation-authorized Gateway API:

| Method | Route | Description |
|---|---|---|
| `POST` | `/fmu/api/v1/simulations/jobs` | Queue one cancellable simulation |
| `POST` | `/fmu/api/v1/simulations/batches` | Queue up to 8 scenarios for the same FMU |
| `GET` | `/fmu/api/v1/simulations/{id}` | Check status and batch progress |
| `POST` | `/fmu/api/v1/simulations/{id}/cancel` | Cancel an active run or remaining cases |
| `GET` | `/fmu/api/v1/simulations/{id}/result` | Read final or terminal partial output |
| `GET` | `/fmu/api/v1/simulations/history?limit=20&offset=0` | Browse history for the current reservation |

For example, a batch body contains shared options and one parameter map per case:

~~~json
{
  "labId": "lab-01",
  "reservationKey": "reservation-123",
  "options": {"startTime": 0, "stopTime": 10, "stepSize": 0.01},
  "scenarios": [
    {"label": "low", "parameters": {"ambient": 285}},
    {"label": "high", "parameters": {"ambient": 305}}
  ]
}
~~~

The `202 Accepted` response includes the job ID and its public status and result URLs. Results are
read after the job reaches a terminal state. Gateway authorization binds each read to the same
lab and reservation that submitted the work. The Executor owns admission, quotas, execution limits,
retention, cancellation behavior, and result evidence; see its
[jobs, batches, cancellation, and history contract](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md#jobs-batches-cancellation-and-history).
Gateway request bounds and variables allowed by the linked AAS policy are documented in the
[configuration reference](reference/configuration.md) and [AAS guide](aas-support.md).


## Complete provider web apps

A provider app can use the same reservation-scoped session as `proxy.fmu`. Marketplace embeds the
app in a sandboxed iframe and requests a short-lived, reservation-scoped connection grant.
Simulation data then travels directly from the browser to Gateway and the private Station Executor.

```text
POST /fmu/api/v1/fmu/connection/{labId}?reservationKey=...
```

This protected endpoint uses the same authorization, rate bucket, ticket issuance, issuer routing
and WS URL derivation as the proxy download. It returns `protocolVersion`, `gatewayWsUrl`, `labId`,
`reservationKey`, `sessionTicket` and `ticketExpiresAt`, with `Cache-Control: no-store`. Marketplace
keeps its resource credential server-side and delivers only this temporary grant to the requesting
iframe. No model binary or runtime secret is exposed.

Browser clients send the ticket in their first `session.create` frame on `WSS
/fmu/api/v1/fmu/sessions`. They use the existing redemption, on-chain reservation checks, session
evidence, revocation and Station expiry path. The WS route accepts an opaque iframe `Origin: null`,
but does not translate cookies to bearer credentials. Such a browser needs its short-lived
reservation-scoped ticket. This exception is limited to the WS endpoint; it does not relax HTTP
CORS. Native proxy clients retain their existing ticket flow.

Browser applications use the same reservation-bound Gateway connection grant and WebSocket
facade. The Executor README documents the underlying message capabilities, including dense sample
advancement. The host-app contract and optional client SDK are documented in the
[Marketplace provider app guide](https://github.com/DecentraLabsCom/Marketplace/blob/feature/digital-twins/docs/provider/digital-twin-threejs-app-contract.md).
A provider app is a complete presentation, while GLB assets use the Marketplace's generated controls
and indicators.

Local-only demos use the `fmu-local-dev` Executor and the same WS manager. An additional private
preview route is registered only when `FMU_LOCAL_DEV_MODE` is enabled, and requires the local
Executor bridge secret. It issues bounded, one-use preview tickets for virtual local reservations;
it never grants real reservation access or emits on-chain session evidence. The loopback-only demo
Nginx overlay serves WS on port 8081 so a development certificate is not needed in the browser.
These preview routes are not enabled by production Full/Lite configuration.

## Gateway-to-Station contract

The Gateway calls the Executor only on its private Station channel and forwards a validated
`gatewayContext` with the effective lab, FMU access key, reservation and claims. Station independently
checks the resource and reservation scope before execution. See the Executor's
[internal API](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md#internal-api)
for endpoint and authentication details.

## Security and operational rules

- Never publish or return the real FMU through Marketplace, Gateway or proxy downloads.
- Keep Station APIs on a private network and require the internal token or mTLS.
- Enforce the reservation window at proxy download, session creation and execution time.
- Treat `sessionTicket` as a short-lived capability: reservation bound, checked against current
  on-chain state and never logged in plaintext.
- Rate-limit proxy downloads and real-time session creation.
- Keep physical-lab flows unchanged; FMU-specific behavior applies only when `resourceType=fmu`.

## Relationship to adjacent standards

FMI/FMU is the protected execution and interoperability layer. It is not a complete digital-twin
information model. The natural complementary layers are:

- **SSP** for composed systems and systems-of-systems;
- **AAS** for stable identity, standard semantic metadata, packaging and discovery. DecentraLabs
  uses IDTA 02005 for simulation-model metadata, IDTA 02020 for capabilities and IDTA 02017 for
  interface affordances; reservation-scoped invocation remains outside the AAS server;
- **OPC UA** for live industrial equipment, telemetry, commands and OT/IT integration; and
- **DCP** only for premium hard-real-time, HIL/SIL or demanding distributed co-simulation scenarios.

## Detailed implementation references

Use these documents when the work is implementation- or deployment-specific:

- [AAS support](aas-support.md) — synchronization, metadata, and FMI variable access policy.
- [FMU visual assets](aas-fmu-visual-assets.md) — GLB and complete Three.js asset setup and AAS
  linking.
- [FMU Runner](../fmu-runner/README.md) — Gateway facade, endpoints, backend modes, tests and Docker
  operation.
- [FMU Executor README](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md) — runtime
  configuration, private API, validation, limits, isolation and FMI conformance.
- [Gateway FMU development data](../fmu-data/README.md) — local fixture and sync behavior.
- [FMU proxy runtime](../fmu-proxy-runtime/README.md) — runtime binary drop path and platform
  packaging.
- [FMU proxy runtime source](../fmu-proxy-runtime-src/README.md) — native runtime source, build,
  release and platform validation.
- [FMU proxy runtime architecture](../fmu-proxy-runtime-src/ARCHITECTURE.md) — FMI-to-Gateway
  mapping, responsibilities and runtime state.

## Acceptance checklist

### Provider

- [ ] Real FMU is provisioned and validated on Lab Station.
- [ ] The resource uses `resourceType=fmu` and the correct `accessKey`.
- [ ] `station` mode, internal Station authentication and the FMU audience are configured for
  production.
- [ ] Availability, unavailability, terms and documentation are complete.
- [ ] Proxy downloads and real-time session creation are rate-limited.
- [ ] The generated proxy has been tested in at least one target FMI tool.

### User

- [ ] A valid reservation exists for the requested window.
- [ ] The proxy was downloaded from the authorized Gateway endpoint.
- [ ] The artifact hash/signature was verified when supplied.
- [ ] The proxy was imported as an FMI Co-Simulation FMU.
- [ ] The FMI tool uses the intended simulation time mode and step size.
- [ ] The session is terminated when the simulation is complete.
