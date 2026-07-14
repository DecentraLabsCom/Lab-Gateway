# Asset Administration Shell (AAS) Support

This document is the operational guide for DecentraLabs' Asset Administration Shell support. AAS is an optional semantic and discovery layer around provider resources. It complements the FMI/FMU execution layer; it does not execute models, control equipment or replace reservations.

## What AAS adds

AAS gives a resource a stable digital identity and a structured place for technical, commercial and operational metadata:

- FMUs use simulation-model metadata, FMI ports, capabilities, tools, units, licensing and model-file integrity information.
- Physical labs use nameplate, technical-data, documentation and contact information.
- Marketplace discovery is provider-hosted: Marketplace reads the AAS shell from the Gateway that publishes the resource.
- AAS is optional. If a provider has no AAS data, the resource page and its reservation/access flow continue to work unchanged.

## Two perspectives at a glance

| Provider | User / consumer |
| --- | --- |
| Hosts or selects an AAS server for the Full Gateway. | Reads AAS information from the resource page when available. |
| Generates or imports shells for FMUs and physical labs. | Uses the shell to compare identity, capabilities, compatibility and constraints. |
| Enriches metadata in `lab-manager`. | Can open raw AAS JSON or download an AASX package when exposed. |
| Controls external AAS links and synchronization timing. | Does not need to configure AAS to reserve or use a resource. |
| Keeps AAS data at the provider Gateway or configured external server. | Treats AAS as descriptive information, not as an authorization grant. |

## Architecture and deployment modes

Each provider Gateway owns its AAS stack. Marketplace does not maintain an AAS database and must not use a resource's operational `accessURI` as the AAS base URL. The provider Gateway base is derived from the provider's canonical `authURI`; the stable shell ID is then requested from `/aas/shells/{aasId}`.

~~~mermaid
flowchart LR
    Marketplace["Marketplace"] -->|GET provider-gateway/aas/shells/{id}| Gateway["Provider Lab Gateway"]
    Gateway --> OpenResty["OpenResty /aas"]
    OpenResty --> BaSyx["Bundled BaSyx or external AAS server"]
    LabManager["Provider lab-manager"] -->|admin sync| Gateway
    FmuRunner["fmu-runner"] --> BaSyx
    OpsWorker["ops-worker"] --> BaSyx
~~~

### Full Gateway

The Full Gateway owns the provider control plane and may expose AAS. The bundled BaSyx service is optional and is enabled with the `aas` Compose profile:

~~~bash
docker compose --profile aas up -d
# or
COMPOSE_PROFILES=aas docker compose up -d
~~~

The bundled deployment persists AAS data through MongoDB and named volumes.

### Lite Gateway

Lite Gateways delegate identity and control-plane responsibilities to a Full Gateway. AAS and AAS administration endpoints are disabled in Lite mode. A Lite deployment may still serve FMU and physical-lab access, but it is not the provider AAS authority.

### External AAS server

Set `BASYX_AAS_URL` to use a provider-managed BaSyx or another compatible AAS REST server instead of the bundled service. The same provider-side sync endpoints remain in use. An empty value disables AAS synchronization cleanly.

## Provider guide

### 1. Choose the AAS source

The provider can use one of three modes:

1. Bundled BaSyx in the Full Gateway, enabled with the `aas` profile.
2. An external AAS server configured through `BASYX_AAS_URL`.
3. No AAS, leaving the rest of the Gateway unchanged.

Do not enable AAS only to make a resource executable. FMU execution continues through the FMU proxy/runtime path, and physical-lab access continues through the existing Gateway/Station flows.

### 2. FMU shell synchronization

Use the provider's `lab-manager` to run:

~~~text
POST /aas-admin/fmu/{accessKey}/sync
~~~

The endpoint is protected by the existing `lab_manager_access.lua` mechanism (admin header, cookie or token) and is not a public booking endpoint. It:

1. calls the internal FMU `describe` operation;
2. generates an IDTA 02006 `SimulationModels` submodel, or ingests an uploaded `.aasx` file;
3. adds optional description, license, documentation URL and contact metadata;
4. creates or replaces the shell and submodels in BaSyx.

The optional `labId` parameter lets the provider keep a stable AAS identity anchored to a resource ID rather than to an operational FMU `accessKey`. The endpoint returns a disabled result when AAS is intentionally not configured and an upstream error when the configured AAS server cannot be reached.

The lab-manager FMU panel supports generated shell synchronization, optional metadata, explicit `.aasx` upload and an optional `labId` override.

### 3. Physical-lab shell synchronization

`ops-worker` is responsible for physical-lab shells because it already owns heartbeat persistence, host information and operational telemetry:

~~~text
POST /aas-admin/lab/{labId}/sync
POST /api/aas-sync
~~~

Heartbeat persistence best-effort synchronizes the TechnicalData submodel. The lab-manager **Sync AAS** action can synchronize all labs associated with a host. This path does not depend on `fmu-runner`.

### 4. Link an existing external AAS

When the provider already owns a shell elsewhere, it can link the operational FMU key to that shell instead of generating a new one:

~~~text
POST   /aas-admin/fmu/{accessKey}/aas-link
GET    /aas-admin/fmu/{accessKey}/aas-link
DELETE /aas-admin/fmu/{accessKey}/aas-link
GET    /aas-admin/resolve-aas-id?shellId=<shell-id>
~~~

The Gateway keeps the Marketplace-facing stable shell ID and resolves it to the linked external AAS. The link is managed from the lab-manager **Link Existing AAS** panel.

### 5. Identity and versioning policy

The stable shell identity is:

~~~text
urn:decentralabs:lab:{labId}
~~~

`accessKey` is operational and versioned. If the FMU changes but its resource identity remains the same, re-sync the existing shell without changing its AAS ID. A resource-type change is restricted by the on-chain resource/listing policy and must not silently turn a published resource into another type.

## Resource models and submodels

| Resource | Main submodels | Typical information |
| --- | --- | --- |
| FMU simulation | IDTA 02006 `SimulationModels`, Documentation, LicenseInfo | Summary, FMI ports, causality, quantities, tools, tolerances, capabilities, model-file hash and units. |
| Physical laboratory | Nameplate, TechnicalData, Documentation, ContactInformation | Lab ID, host, type, network address, MAC, mapped lab IDs and heartbeat state. |

The FMU `SimulationModels` submodel currently includes:

- `Ports` mapped from FMI variables;
- `PortCausality`, `QuantityKind` and port descriptions;
- `SimulationToolSupport` with tool, dependency and version information;
- `Tolerance` and a capabilities block;
- `ModelFile` with SHA-256 integrity data when the real FMU is available;
- a separate `UnitDefinitions` submodel with SI exponents and display units; and
- optional license, documentation and contact properties.

The generator targets approximately 95% conformance with IDTA 02006 based on the currently implemented elements. Conformance is not a substitute for provider validation of the actual model and license metadata.

## Consumer guide

### Marketplace behavior

Marketplace requests the provider shell through a server-side route with SSRF protection and rate limiting. The resource page shows an AAS panel only when the provider Gateway returns a shell. A 404 or unavailable optional AAS server leaves the normal resource page unchanged.

When available, the panel can show:

- asset type and stable AAS ID;
- host and network information for physical labs;
- mapped laboratory IDs and last synchronization information;
- FMU description, license, documentation URL and contact; and
- a link to the raw shell or a downloadable `.aasx` package.

AAS metadata helps a consumer understand and compare a resource. It does not replace authentication, a reservation, a session ticket, a physical-lab access token or the FMI proxy authorization flow.

### How to interpret an FMU AAS

Use `SimulationModels` to inspect the model's summary, exposed ports, causality, supported tools, capabilities, units, tolerance and license. Then verify that the Marketplace listing and reservation conditions match the intended use. A shell is provider-published metadata; the consumer should not assume that an AAS property alone grants execution rights.

### How to interpret a physical-lab AAS

Use Nameplate and TechnicalData to understand the identity and current operational description of the lab. Live availability and reservation state still come from Marketplace and the control plane, not from a cached AAS shell.

## Routing and security

OpenResty separates public read access from provider administration:

~~~text
/aas/                -> BaSyx or BASYX_AAS_URL
/aas-admin/fmu/      -> fmu-runner
/aas-admin/lab/      -> ops-worker
~~~

The administration routes require `LAB_MANAGER_TOKEN` through the shared lab-manager access guard, even when the Gateway is reachable from a private network. AAS write operations must not reuse public booking/JWT endpoints.

The provider should also:

- protect the AAS server and admin routes with the Gateway network policy;
- avoid putting secrets or bearer tokens in shell properties;
- validate and sanitize external URLs, especially documentation and AAS link targets;
- keep AAS data and BaSyx storage backed up according to provider policy; and
- treat license and contact fields as published metadata visible to consumers.

## Current implementation status

Implemented in the Gateway ecosystem:

- optional bundled BaSyx service for Full Gateway deployments;
- external AAS server selection through `BASYX_AAS_URL`;
- FMU shell generation and `.aasx` ingestion in `fmu-runner`;
- physical-lab Nameplate and TechnicalData generation in `ops-worker`;
- explicit lab-manager synchronization and optional FMU metadata fields;
- Marketplace shell discovery, AAS panel and AASX download;
- transparent links to existing external AAS shells; and
- IDTA 02006 simulation-model mapping including FMI ports, units and integrity metadata.

The following remain future work:

- multi-Gateway AAS federation and cross-provider shell aggregation;
- on-chain registration and verification of AAS IDs; and
- Verifiable Credentials/DIDs attached to AAS licensing or provenance data.

These items are not prerequisites for the current AAS MVP. Shell generation, publication and discovery work independently of blockchain; existing provider identity and Gateway resolution controls remain the security boundary.

## Acceptance checklist

### Provider

- [ ] Decide bundled, external or disabled AAS mode.
- [ ] Keep the Full/Lite deployment distinction explicit.
- [ ] Synchronize FMU shells from `lab-manager` or ingest a validated `.aasx`.
- [ ] Verify the stable `labId`-anchored AAS ID and operational `accessKey`.
- [ ] Add only metadata intended for consumer visibility.
- [ ] Confirm the AAS server is persistent and backed up.
- [ ] Test shell retrieval through the provider Gateway, not only directly against BaSyx.

### Consumer

- [ ] Treat AAS as descriptive metadata, not an access credential.
- [ ] Check the model's ports, capabilities, tools, units and license.
- [ ] Check physical-lab technical data separately from live availability.
- [ ] Follow the normal Marketplace reservation and access flow.
- [ ] Use raw JSON/AASX only as an additional integration artifact and validate it against the provider's published terms.



