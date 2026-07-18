# FMI/FMU Support

This document is the operational guide for DecentraLabs' FMI/FMU support. It consolidates the remote real-time specification, implementation status and compatibility evidence into one provider- and user-oriented reference. It is the product and deployment entry point; the implementation references at the end retain the detailed runtime, build and storage instructions.

## What DecentraLabs provides

DecentraLabs exposes a protected FMU as a reservation-scoped remote simulation:

- The provider's real `.fmu` remains on Lab Station and is never delivered to the user.
- Marketplace does not upload the real model. The provider provisions it on the execution station and publishes an `accessKey` reference.
- The user downloads a generated `proxy.fmu`, imports it into a native FMI tool and runs the model through the Gateway.
- A short-lived, single-use session ticket binds the real-time session to the user, lab and reservation.
- Reservation windows, availability rules, terms and existing lab metadata apply to FMU resources in the same way as to physical laboratories.

The current product target is FMI 2.0.3 Co-Simulation. FMI 3.0 Co-Simulation is supported on the validated runtime paths described below. Model Exchange and Scheduled Execution are outside the current product scope.

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

Marketplace and `blockchain-services` handle listings, reservations, availability, authorization, session-ticket issuance and audit-related decisions.

### Delivery plane

The Gateway obtains the model description from the real FMU and creates the proxy archive. The proxy contains only:

- `modelDescription.xml` describing the exposed FMI interface;
- proxy runtime binaries for supported platforms; and
- `resources/config.json` with reservation-scoped connection data.

It does not contain the provider's model binaries or model assets.

### Execution plane

Lab Station stores, loads and executes the real FMU. In production, the Gateway must not require the real FMU in its own filesystem.

The Gateway retains a `local` backend for development, smoke tests and automated tests. `station` is the production backend and forwards execution through the private Station APIs.

## Provider guide

### 1. Provision and validate the FMU

Place the real model in the Station FMU store. The canonical layout is one of:

~~~text
fmu-data/<accessKey>.fmu
fmu-data/<accessKey>/model.fmu
~~~

Before publication, validate that the archive is parseable, has a valid model description and GUID, and exposes Co-Simulation. Invalid or untrusted models can be quarantined; quarantined FMUs are excluded from the catalogue and session creation.

Internal Station operations include:

~~~text
GET  /internal/health
GET  /internal/fmu/catalog  (X-FMU-Access-Key header)
GET  /internal/fmu/describe  (X-FMU-Access-Key header)
POST /internal/fmu/validate/{accessKey}?auto_quarantine=true
POST /internal/fmu/quarantine/{accessKey}
DELETE /internal/fmu/quarantine/{accessKey}
~~~

These endpoints are internal. The public user does not call them directly.

### 2. Publish the resource

Register the resource in Marketplace with:

~~~text
resourceType = fmu
accessURI    = <public provider Gateway>
accessKey    = <Station FMU identifier>
~~~

The `accessKey` is an operational/versioned reference. It is not a substitute for the stable resource identity used by Marketplace and the reservation system.

### 3. Configure the execution backend

For the production Station path, configure the Gateway with the Station internal URL, internal session token and:

~~~text
FMU_BACKEND_MODE=station
FMU_JWT_AUDIENCE=https://<public-gateway-origin>/fmu
~~~

For isolated local development/tests, start the `fmu-local-dev` Compose
profile. It sets `FMU_BACKEND_MODE=local` and `FMU_LOCAL_DEV_MODE=true` in a
container that has only the internal local edge network and no Station,
session-observer or control-plane secrets. Local batch requests use one
killable worker process per simulation. Native local realtime requires the
additional explicit switch `FMU_LOCAL_REALTIME_ENABLED=true`; keep it false
outside an isolated test environment. The internal Station channel is private and
authenticated with an internal token or mTLS; the public booking JWT is not
the sole protection of the internal channel.

### 4. Manage interface disclosure

The generated proxy must expose enough FMI metadata for interoperability: variables, types, causality, variability and units. This is intentional FMI interface disclosure. For sensitive models, providers may use private aliases such as `u1` and `y1`; aliasing reduces semantic leakage but does not replace authorization, reservation or network controls.

### 5. Preserve common resource metadata

FMU listings use the same functional metadata as physical labs:

- images and documentation;
- terms and conditions;
- availability and unavailability windows; and
- allowed reservation and usage timing.

These fields are used for catalogue display, reservation validation, execution-window enforcement and auditability.

## User guide

### 1. Reserve the FMU

Create a reservation in Marketplace. The reservation must be active and its availability and time window must be valid before a proxy can be downloaded or a real-time session can be created.

### 2. Download the proxy

Request the reservation-scoped artifact:

~~~text
GET /api/v1/fmu/proxy/{labId}?reservationKey=<reservation-key>
~~~

The request requires an authenticated session and authorization over the reservation. The response is an `application/octet-stream` FMU archive. The Gateway may also return:

- `X-Proxy-Artifact-Sha256`, the SHA-256 hash of the generated artifact; and
- `X-Proxy-Artifact-Signature`, an optional `hmac-sha256=<hex>` signature when the provider configured artifact signing.

Verify the hash, and the signature when present, before importing the proxy. If the embedded ticket expires or has already been used, regenerate the proxy; tickets are not reusable.

### 3. Import and run it in an FMI tool

Import `proxy.fmu` as a normal Co-Simulation FMU. The proxy opens a secure WebSocket to the provider Gateway, exchanges the one-shot ticket and maps FMI calls to the remote real-time API. No local DecentraLabs agent is needed.

The externally advertised Gateway facade is:

~~~text
WSS /fmu/api/v1/fmu/sessions
~~~

Internal `fmu-runner` paths may appear as `/api/v1/...` behind the OpenResty route.

### 4. Session lifecycle

The proxy and Gateway use these operations:

~~~text
session.create          model.describe / model.description
sim.initialize          sim.getState
sim.start               sim.pause / sim.resume / sim.reset
sim.step                sim.runUntil
sim.setInputs           sim.getOutputs
sim.subscribeOutputs    sim.unsubscribeOutputs
session.ping             session.attach
session.terminate
~~~

Every request carries a `requestId`; responses and events echo it where applicable. `session.terminate` is idempotent. A session is forcibly closed when the reservation window expires.

A ticket-based `session.create` is bound to the user, lab and reservation, has a short configurable TTL (default 120 seconds) and can be consumed only once. Reuse returns `SESSION_TICKET_ALREADY_USED`. Other expected errors include `SESSION_TICKET_INVALID`, `SESSION_TICKET_EXPIRED`, `RESERVATION_NOT_ACTIVE`, `SESSION_EXPIRED`, `RATE_LIMITED` and `INTERNAL_ERROR`.

### 5. Simulation time and streaming

`sim.initialize.options.timeMode` supports:

- `simtime`: advance simulated time as quickly as possible;
- `realtime`: try to follow the wall clock.

`simtime` is the recommended default.

Streaming uses bounded per-session queues. Output events include `seq` and `dropped`, and subscriptions can set `periodMs`, `maxHz` and `maxBatchSize`.

## Gateway-to-Station contract

The private Station API includes:

~~~text
GET  /internal/health
GET  /internal/fmu/catalog  (X-FMU-Access-Key header)
GET  /internal/fmu/describe  (X-FMU-Access-Key header)
POST /internal/fmu/simulations/run       (JSON body: accessKey)
POST /internal/fmu/simulations/stream    (JSON body: accessKey)
WSS  /internal/fmu/sessions
~~~

Gateway-to-Station messages preserve `requestId` and include a validated `gatewayContext` containing the effective `labId`, `accessKey`, `reservationKey` and claims. Station independently checks resource, reservation and expiry values before executing a model operation.

## Supported clients and current status

| Client/runtime | Status | Notes |
| --- | --- | --- |
| Python FMI client (`fmpy`), FMI 2 Co-Simulation | Validated | Proxy loading and execution tests pass. |
| `fmpy`, FMI 3 scalar Co-Simulation on `win64` | Validated | Live `Stair.fmu` path. |
| `fmpy`, FMI 3 dimensioned Co-Simulation on `win64` | Validated | Live `StateSpace.fmu` path. |
| FMI 3 integer family, Binary and Clock runtime support | Implemented/partially validated | Broader tool and model coverage remains a validation item. |
| OpenModelica / OMSimulator | Validated | Standalone proxy, composed local+remote simulation, SSP export and stepwise control. |
| Classic `omc importFMU(...)` | Out of scope | OMSimulator is the intended OpenModelica path. |
| Simulink / MATLAB | Pending | Requires a manual smoke test where the tool is available. |
| `linux64` proxy runtime | Working | End-to-end validation exists for downloaded proxy artifacts. |
| `darwin64` proxy runtime | Pending | Source/build path exists; a validated native binary is still pending. |
| FMI 3 Model Exchange | Out of scope | Not aligned with the current protected Co-Simulation product. |
| FMI 3 Scheduled Execution | Out of scope | Reserved for a future specialised offering. |

Useful validation scripts are under `Lab Gateway/tests/integration/`, including `verify-openmodelica-omsimulator.ps1`, while FMU loading tests are under `Lab Gateway/fmu-runner/tests/`.

## Security and operational rules

- Never publish or return the real FMU through Marketplace, Gateway or proxy downloads.
- Keep Station APIs on a private network and require the internal token or mTLS.
- Enforce the reservation window at proxy download, session creation and execution time.
- Treat `sessionTicket` as a short-lived capability: single use, reservation bound and never logged in plaintext.
- Rate-limit proxy downloads and real-time session creation.
- Keep physical-lab flows unchanged; FMU-specific behavior applies only when `resourceType=fmu`.

## Relationship to adjacent standards

FMI/FMU is the protected execution and interoperability layer. It is not a complete digital-twin information model. The natural complementary layers are:

- **SSP** for composed systems and systems-of-systems;
- **AAS** for stable identity, semantic metadata, packaging, discovery and marketplace-facing digital-twin information;
- **OPC UA** for live industrial equipment, telemetry, commands and OT/IT integration; and
- **DCP** only for premium hard-real-time, HIL/SIL or demanding distributed co-simulation scenarios.

## Detailed implementation references

Use these documents when the work is implementation- or deployment-specific:

- [FMU Runner](../fmu-runner/README.md) — Gateway facade, endpoints, backend modes, tests and Docker operation.
- [FMU data layout](../fmu-data/README.md) — provider-scoped FMU storage and provisioning layout.
- [FMU proxy runtime](../fmu-proxy-runtime/README.md) — runtime binary drop path and platform packaging.
- [FMU proxy runtime source](../fmu-proxy-runtime-src/README.md) — native runtime source, build and release procedures.
- [FMU proxy runtime architecture](../fmu-proxy-runtime-src/ARCHITECTURE.md) — FMI-to-Gateway mapping, responsibilities and runtime state.

## Acceptance checklist

### Provider

- [ ] Real FMU is provisioned and validated on Lab Station.
- [ ] The resource uses `resourceType=fmu` and the correct `accessKey`.
- [ ] `station` mode, internal Station authentication and the FMU audience are configured for production.
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
