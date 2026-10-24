# FMI/FMU Support

This document is the operational guide for DecentraLabs' FMI/FMU support. It consolidates the remote real-time specification, implementation status and compatibility evidence into one provider- and user-oriented reference. It is the product and deployment entry point; the implementation references at the end retain the detailed runtime, build and storage instructions.

## What DecentraLabs provides

DecentraLabs exposes a protected FMU as a reservation-scoped remote simulation:

- The provider's real `.fmu` remains on Lab Station and is never delivered to the user.
- Marketplace does not upload the real model. The provider provisions it on the execution station and publishes an `accessKey` reference.
- The user downloads a generated `proxy.fmu`, imports it into a native FMI tool and runs the model through the Gateway.
- A short-lived, reservation-bound session ticket binds the real-time session to the user, lab and reservation.
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

The Gateway does not execute FMUs in-process. Its `fmu-local-dev` profile
points the facade at the shared FMU Executor container through the same private
HTTP/WSS contract used by Lab Station. Production uses `station` mode to
forward through the private Station APIs. When no Executor is configured, the
local backend is limited to listing and reading metadata; run, stream and
realtime requests require a remote Executor.

## Batches, cancellation, and simulation history

Clients can submit one asynchronous simulation or a small batch of parameter
scenarios through the reservation-authorized Gateway API:

| Method | Route | Description |
|---|---|---|
| `POST` | `/api/v1/simulations/jobs` | Queue one cancellable simulation |
| `POST` | `/api/v1/simulations/batches` | Queue up to 8 scenarios for the same FMU |
| `GET` | `/api/v1/simulations/{id}` | Check status and batch progress |
| `POST` | `/api/v1/simulations/{id}/cancel` | Cancel an active run or remaining cases |
| `GET` | `/api/v1/simulations/{id}/result` | Read final or terminal partial output |
| `GET` | `/api/v1/simulations/history?limit=20&offset=0` | Browse history for the current reservation |

For example, a batch body contains shared options and one parameter map per
case:

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

The `202 Accepted` response includes the job ID and its public status and
result URLs. Results are read after the job reaches a terminal state. A
cancelled batch keeps the completed cases as a partial result and stops the
current worker plus all cases not yet started.

Each request remains bound to its authorized Gateway, lab, reservation and
pseudonymous user claim. A different reservation receives no indication that
the job exists. By default, each reservation can start 100 scenarios per UTC
day. A batch case, single run, stream request, realtime initialization or
reset consumes one start. Realtime input updates use separate per-reservation
rate and byte budgets, so they do not spend scenario starts. Runs are capped
at 10,000 communication steps; a batch is capped at 20,000 total steps.
Requests may set at most 32 parameters using no more than 16 KiB of parameter
JSON. The signed Gateway context may also carry an `fmuExecutionPolicy` with
lower per-model limits for daily scenarios, steps, CPU seconds, memory and
result bytes; Station hard limits still apply.

Admission is immediate across interactive sessions, runs, streams, jobs and
validation probes. When no shared Station slot is available, the request gets
HTTP 429 `STATION_CAPACITY_EXHAUSTED` before its scenario quota is charged.
`queued` in the accepted job response means the reserved worker is starting;
the Executor does not keep an unbounded waiting queue.

Jobs retain separate authorization and reservation deadlines. The signed
authorization expiry may be shorter than the on-chain reservation end. The
Gateway forwards both values, and the Executor checks them before every batch
case and during a running worker. The resulting job records whether execution
stopped because authorization expired or because the reservation ended.

Run, stream, job and batch options accept `outputVariables` and
`outputSampleEverySteps` (default `1`) to limit collected output. The FMU used
by each accepted job is a read-only content-addressed snapshot; replacing the
provisioned file cannot switch the model between batch cases. Results include
technical evidence with the FMU SHA-256, Executor version/commit, FMPy and
platform versions, effective inputs/options/policy, finish reason, warnings
and result hash. This provider-side evidence supports reproduction but is not
an independent institutional attestation. A successful NDJSON stream puts the
same evidence on its final `sim.done` record; its result hash covers the data
lines sent before that record.

History expires after 7 days by default. The Executor also caps history at
10,000 records, 8 MiB for one stored result and 256 MiB of stored results in
total. Parameters and options remain available on each retained job; result
data may be pruned earlier when the total result-size cap is reached. The
limits can be configured in the Executor environment.

## Provider guide

### 1. Provision and validate the FMU

Place the real model in the Station FMU store. The canonical layout is one of:

~~~text
fmu-data/<accessKey>.fmu
fmu-data/<accessKey>/model.fmu
~~~

Before publication, call Station validation and review the separate
`archiveValid`, `modelDescriptionValid`, `stationCompatible` and
`executionChecked` values. The report includes the Station OS/architecture,
FMI version and capabilities, expected native binary, compressed and expanded
archive sizes and limits, model-description size, and whether native
dependencies were checked. A binary being present establishes compatibility
only; dependencies are checked by the
optional worker probe. For that stronger check, use `probe=true`, which loads
and initializes the FMU in an isolated worker. A passing initialization does
not certify all later simulation paths. Invalid or untrusted models can be
quarantined; quarantined FMUs are excluded from the catalogue and session
creation.

Internal Station operations include:

~~~text
GET  /internal/health
GET  /internal/fmu/catalog  (X-FMU-Access-Key header)
GET  /internal/fmu/describe  (X-FMU-Access-Key header)
POST /internal/fmu/validate/{accessKey}?probe=true&auto_quarantine=false
POST /internal/fmu/quarantine/{accessKey}
DELETE /internal/fmu/quarantine/{accessKey}
~~~

These endpoints are internal. The public user does not call them directly.
The describe endpoint accepts `publicOnly=true` for consumers that need the
exchange interface without the FMU's local implementation variables. Gateway
public describe and proxy metadata requests use this reduced form for large
FMUs; it still parses the complete model description through FMPy, and does
not suppress validation errors.

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

The Station channel uses one Gateway-owned internal token, not a browser
credential or a certificate. `setup.sh`/`setup.bat` generates
`FMU_STATION_INTERNAL_TOKEN` and synchronizes it as a Compose secret for
`fmu-runner`, the embedded backend and `ops-worker`. Register the Station in
the Gateway host inventory and set `FMU_STATION_BASE_URL` to its executor URL
(`http://<station-address>:8091` by default). If the URL hostname is not the
inventory address, set `FMU_STATUS_STATION_HOST` to the registered host name.

From Lab Manager > Lab Station Ops, the configured Station row exposes a
`Link FMU token` action. The operation follows the Station management contract:
Windows v2 over WinRM writes the token to the machine-level
`FMU_INTERNAL_TOKEN` variable and starts or restarts
`LabStation\BackgroundService`; Linux v3 over SSH stores it in the
root-owned `/etc/decentralabs/lab-station/secrets/fmu-internal-token.env` file
with mode `0600`, then starts or restarts `decentralabs-labstation-fmu`.
Releasing the token removes the Windows machine variable and restarts the
background task; on Linux it removes the secret file and stops the FMU service.
Once linked, the row changes to `Release FMU token` and other Station rows
remain disabled. The token is never returned to the browser. A Gateway cannot
link a second host: the selected host must resolve to the single Station
represented by `FMU_STATION_BASE_URL`/`FMU_STATUS_STATION_HOST`.

The panel status is authenticated end-to-end through
`GET /internal/fmu/capacity`; the unauthenticated `/internal/health` response
alone is not considered proof that the Gateway and Station share a token.

The Station is the single operational capacity authority. Set its
`FMU_MAX_SESSIONS` value to the effective execution limit; the provider
backend reads `GET /internal/fmu/capacity` before FMU publication and provider
confirmation, and rejects metadata without a positive off-chain
`maxConcurrentUsers` declaration or whose declaration exceeds that limit. The
contract stores `resourceType`; `maxConcurrentUsers` remains provider metadata
and is revalidated inside the provider confirmation lock. A capacity read
failure leaves a pending reservation retryable.

For isolated local development/tests, start the `fmu-local-dev` Compose
profile. The Gateway facade delegates batch, stream and realtime execution to
`fmu-executor-local`, pulled from the versioned image configured by
`FMU_EXECUTOR_IMAGE` (default `ghcr.io/decentralabscom/fmu-executor:0.2.1`).
No separate `FMU-Executor` source checkout is required. The Executor shares
`./fmu-data` with the Gateway facade and is reachable only over the internal
local edge. It receives a dedicated internal token; the Gateway also receives
the session-observer credential required for authenticated ticket redemption
and durable session observation. The public booking JWT is not the sole
protection of the internal channel.

Gateway no longer contains an in-process FMU execution engine. It still uses
FMPy to read model descriptions for AAS metadata and proxy generation. The
development profile runs the shared FMU Executor implementation in a container;
Lab Stations package that implementation in their own runtime bundles.

JWT key retrieval is independent of the FMU execution backend. In Full mode the
runner uses `http://blockchain-services:8080/auth/jwks`; in Lite mode it uses
the external issuer's JWKS endpoint. `AUTH_JWKS_URL` may explicitly override
that selection, but it is subject to the same HTTPS requirement; HTTP is only
accepted for loopback/private hosts used by local Compose networking. The local profile reaches the Full-mode endpoint through the
dedicated internal `fmu_auth` network.

The Linux Executor applies CPU, memory, per-file and descriptor limits,
Landlock rules that limit reads to the runtime and pinned FMU and writes to
the private work directory, and seccomp rules that deny network sockets and
executable child processes; it fails closed if those kernel controls are not
available. The Windows Station uses a Job Object to bound CPU time, memory and
child processes and to terminate the full worker tree. Its FMU worker retains
the Windows service identity, can access files allowed to that identity, is
not network-isolated, and has no aggregate temporary-disk quota. The validation
response's `workerIsolation` field reports these platform-specific controls.
The local Docker profile adds a non-root user, read-only root filesystem,
container resource and process limits, and bounded temporary storage. For
Windows deployments that need filesystem, network, or low-privilege identity
isolation, run the sidecar under a dedicated restricted service account and
apply host policy outside the Executor.

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

Verify the hash, and the signature when present, before importing the proxy. If the embedded ticket expires or the reservation is cancelled, regenerate the proxy. Ticket redemption rechecks the current on-chain reservation state.

### 3. Import and run it in an FMI tool

Import `proxy.fmu` as a normal Co-Simulation FMU. The proxy opens a secure WebSocket to the provider Gateway, exchanges the reservation-bound ticket and maps FMI calls to the remote real-time API. No local DecentraLabs agent is needed.

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

Every request carries a `requestId`; responses and events echo it where applicable. `session.terminate` is idempotent. A session is forcibly closed when the reservation window expires. In Station mode, an unexpected internal WebSocket disconnect detaches the FMU state temporarily; a new authenticated channel can use `session.attach` with the same session binding during the configured grace window.

A ticket-based `session.create` is bound to the user, lab and reservation and has a short configurable TTL (default 120 seconds). It can be reused only while the ticket and the current on-chain reservation remain valid. Other expected errors include `SESSION_TICKET_INVALID`, `SESSION_TICKET_EXPIRED`, `RESERVATION_NOT_ACTIVE`, `SESSION_EXPIRED`, `SESSION_TICKET_RESERVATION_STATE_UNAVAILABLE`, `RATE_LIMITED` and `INTERNAL_ERROR`.

### 5. Simulation time and streaming

`sim.initialize.options.timeMode` supports:

- `simtime`: automatic sessions advance as quickly as the FMU permits;
- `realtime`: automatic sessions follow wall-clock time, scaled by
  `playbackSpeed` (default `1`, range `0.1` to `100`);
- `external`: the caller owns every step. `sim.start`, `sim.resume` and
  `sim.runUntil` are rejected; `sim.step` requires the current
  `currentCommunicationPoint`.

`simtime` is the default for automatic sessions. A proxy FMI runtime advances
through its caller's FMI `doStep` calls and sends each current communication
point to Station. Generated proxy FMUs use `external` by default because the
importing FMI tool owns the step sequence; operators can select another mode
with `FMU_PROXY_TIME_MODE` (`simtime`, `realtime` or `external`). In a generated
proxy, `realtime` paces `doStep` calls against the wall clock; `simtime` leaves
them unpaced. `FMU_PROXY_PLAYBACK_SPEED` sets the realtime multiplier from 0.1
to 100 (default `1`).
FMI 3 proxy instantiation forwards the importer's `earlyReturnAllowed`
negotiation to Station, and `doStep` returns the last successful time and
termination/early-return flags from the remote session.
The proxy's FMI `reset` requests a deferred Station reset, then sends a fresh
`sim.initialize` with the importer's new experiment and retained initial input
values.

Streaming uses bounded per-session queues. Output events include `seq` and `dropped`, and subscriptions can set `periodMs`, `maxHz` and `maxBatchSize`.
The Station limits subscriptions to 60 Hz and 256 samples per batch by default;
automatic `sim.progress` messages are throttled independently from the FMU
communication step. Individual step responses include `requestedTime`,
`timeAdvanced`, `earlyReturn`, `eventOccurred`, `terminateSimulation` and
`finishReason` where applicable. FMI 3 event iteration is completed by the
isolated Station Executor before it returns the step response.

Initialization values are sent in `sim.initialize.options.inputs`. Runtime
`sim.setInputs` accepts only declared FMU inputs, with strict type, range and
array-size validation. Invalid variables are rejected before any setter is
called. Scenario execution and runtime input changes have independent quotas:
the default scenario budget is 100 per reservation per UTC day; input updates
are tracked separately per reservation and FMU (10,000 updates and 64 MiB per
day, 30 updates per 10-second window, 64 KiB per update by default). Operators
can tune the Station limits with the `FMU_MAX_INPUT_*` and
`FMU_INPUT_UPDATE_WINDOW_SECONDS` environment variables.

## Complete provider web apps

A provider app can use the same reservation-scoped session as `proxy.fmu`.
Marketplace embeds the app in a sandboxed iframe and requests a one-use
connection capability. Simulation data then travels directly from the browser
to Gateway and the private Station Executor.

```text
POST /fmu/api/v1/fmu/connection/{labId}?reservationKey=...
```

This protected endpoint uses the same authorization, rate bucket, ticket
issuance, issuer routing and WS URL derivation as the proxy download. It
returns `protocolVersion`, `gatewayWsUrl`, `labId`, `reservationKey`,
`sessionTicket` and `ticketExpiresAt`, with `Cache-Control: no-store`.
Marketplace keeps its resource credential server-side and delivers only this
temporary grant to the requesting iframe. No model binary or runtime secret
is exposed.

Browser clients send the ticket in their first `session.create` frame on
`WSS /fmu/api/v1/fmu/sessions`. They use the existing redemption, on-chain
reservation checks, session evidence, revocation and Station expiry path.
The WS route accepts an opaque iframe `Origin: null`, but does not translate
cookies to bearer credentials. Such a browser therefore needs its one-use
ticket. This exception is limited to the WS endpoint; it does not relax HTTP
CORS. Native proxy clients retain their existing ticket flow.

FMU Executor 0.3.2 adds `sim.advance` for dense timelines:

```json
{"type":"sim.advance","requestId":"batch:1","sessionId":"...","targetTime":60,"maxSamples":256,"stepSize":0.05}
```

It responds with `sim.samples`, the same request/session IDs, `samples` (each
containing `time` and `outputs`), `simTime`, `finished` and `finishReason`.
A batch advances at most 256 steps and has a conservative encoded frame
budget below 1 MB. It includes every intermediate sample; the client requests
the next batch after processing the current one. The session advertises
`capabilities.advanceSamples` and `capabilities.maxOutputHz`; the same output
read budget, model process isolation, step budget and reservation limits apply.

`model.describe` accepts `includeVariables: false` to return defaults and
model metadata without a potentially large variable catalogue. Descriptions
come from the session's immutable FMU snapshot. Apps requiring raw step control
can continue using `sim.step`, `sim.setInputs` and other existing operations.
The current WS executor supports FMI 2/3 Co-Simulation.

The browser SDK and its host v2 schema live in Marketplace's
`packages/digital-twin-app-protocol`. The optional `/fmu-client` entry has no
Marketplace dependency. The `/client` entry composes it with host startup,
authorization and visualization controls. The host protocol carries no run
parameters or output sample stream. GLB and generated interfaces keep their
existing Marketplace execution path. Providers may implement either contract
directly; bundles are not required to include the SDK.

Local-only demos use the `fmu-local-dev` Executor and the same WS manager. An
additional private preview route is registered only when `FMU_LOCAL_DEV_MODE`
is enabled, and requires the local Executor bridge secret. It issues bounded,
one-use preview tickets for virtual local reservations; it never grants real
reservation access or emits on-chain session evidence. The loopback-only demo
Nginx overlay serves WS on port 8081 so a development certificate is not needed
in the browser. These preview routes are not enabled by production Full/Lite
configuration.

## Gateway-to-Station contract

The private Station API includes:

~~~text
GET  /internal/health
GET  /internal/fmu/capacity       (internal token required)
GET  /internal/fmu/catalog  (X-FMU-Access-Key header)
GET  /internal/fmu/describe  (X-FMU-Access-Key header)
POST /internal/fmu/simulations/run       (JSON body: accessKey)
POST /internal/fmu/simulations/stream    (JSON body: accessKey)
WSS  /internal/fmu/sessions       (X-Internal-Session-Token required)
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
- Treat `sessionTicket` as a short-lived capability: reservation bound, checked against current on-chain state and never logged in plaintext.
- Rate-limit proxy downloads and real-time session creation.
- Keep physical-lab flows unchanged; FMU-specific behavior applies only when `resourceType=fmu`.

## Relationship to adjacent standards

FMI/FMU is the protected execution and interoperability layer. It is not a complete digital-twin information model. The natural complementary layers are:

- **SSP** for composed systems and systems-of-systems;
- **AAS** for stable identity, standard semantic metadata, packaging and discovery. DecentraLabs uses IDTA 02005 for simulation-model metadata, IDTA 02020 for capabilities and IDTA 02017 for interface affordances; reservation-scoped invocation remains outside the AAS server;
- **OPC UA** for live industrial equipment, telemetry, commands and OT/IT integration; and
- **DCP** only for premium hard-real-time, HIL/SIL or demanding distributed co-simulation scenarios.

## Detailed implementation references

Use these documents when the work is implementation- or deployment-specific:

- [FMU Runner](../fmu-runner/README.md) — Gateway facade, endpoints, backend modes, tests and Docker operation.
- [FMU Executor source](https://github.com/DecentraLabsCom/FMU-Executor) — shared Station execution service, releases and internal API contract.
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
