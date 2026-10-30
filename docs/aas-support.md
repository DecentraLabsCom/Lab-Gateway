# Asset Administration Shell (AAS) Support

AAS is an optional semantic and discovery layer for provider resources. It
complements the FMI/FMU execution layer; it does not execute models, control
equipment, authorize reservations or replace the existing access flows.

Use this guide to understand the Gateway's AAS architecture, configure a provider AAS source, synchronize or import shells, and interpret the metadata Marketplace displays.

## Contents

- [Purpose and boundaries](#purpose-and-boundaries)
- [Architecture and deployment modes](#architecture-and-deployment-modes)
- [Provider workflows](#provider-workflows)
- [Generated AAS content](#generated-aas-content)
- [FMU visual assets and viewer flow](aas-fmu-visual-assets.md)
- [FMI variable access policy](#fmi-variable-access-policy)
- [Consumer guide](#consumer-guide)
- [Security and routing](#security-and-routing)
- [AASX import limits and validation](#aasx-import-limits-and-validation)
- [Implementation status](#implementation-status)
- [Acceptance checklist](#acceptance-checklist)

## Purpose and boundaries

AAS gives a resource a stable digital identity and a structured place for technical, commercial and operational metadata:

- FMUs use simulation-model metadata, FMI ports, capabilities, tools, units, licensing and model-file integrity information.
- Physical labs use nameplate, technical-data, documentation and contact information.
- Marketplace discovery is provider-hosted: Marketplace reads the AAS shell from the Gateway that publishes the resource.
- AAS is optional. If a provider has no AAS data, the resource page and its reservation/access flow continue to work unchanged.

### Execution capabilities: useful, but not the execution engine

Generated shells now use the standard IDTA `Capability Description` and
`Asset Interfaces Description` submodels. The first describes what a resource
can do; the second describes its HTTP/WebSocket affordances using the W3C WoT
vocabulary. This gives clients an interoperable discovery contract without
turning the AAS server into the execution engine.

The actual invocation remains behind the existing Marketplace, Gateway and
Station authorization paths. FMU execution still uses the protected
`/fmu/api/v1/simulations/*` and `/fmu/api/v1/fmu/sessions` routes, and
physical-lab access still uses the Gateway/Station and Guacamole flow. No
reservation token, session ticket, password or access code is stored in the
shell.

FMU shells describe `RunSimulation`, `CancelSimulation` and, when
Co-Simulation is available, `CreateRealtimeSession` plus the real-time
vocabulary (`Initialize`, `Start`, `Pause`, `Resume`, `Reset`, `Step`,
`RunUntil`, `SetInputs`, `GetOutputs` and `TerminateSession`). Physical-lab
shells describe `PrepareAccessSession`, `StartInteractiveSession`,
`EndInteractiveSession` and `ReadOperationalStatus`. These names are useful
for clients and adapters without pretending that every laboratory exposes the
same physical commands.

### Provider and consumer roles

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
    Marketplace["Marketplace"] -->|GET AAS shell by ID|Gateway["Provider Lab Gateway"]
    Gateway --> OpenResty["OpenResty /aas"]
    OpenResty --> BaSyx["Bundled BaSyx or external AAS server"]
    LabManager["Provider lab-manager"] -->|admin sync| Gateway
    FmuRunner["fmu-runner or fmu-runner-local"] --> BaSyx
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
For local FMU development, start both the `fmu-local-dev` and `aas` Compose
profiles. The Gateway facade reaches bundled BaSyx through the internal
`fmu_aas` network and the local FMU Executor through `fmu_local_edge`. It does
not join Station or control-plane networks. External AAS credentials are not
exposed to the development profile.

### Lite Gateway

Lite Gateways delegate identity and control-plane responsibilities to a Full Gateway. AAS remains opt-in: set `BASYX_AAS_URL` to a provider-managed HTTPS AAS, allowlist its exact hostname in `AAS_ALLOWED_HOSTS`, and configure its dedicated service token. With `FMU_RUNNER_ENABLED=true`, the Digital Twins panel can synchronize generated FMU shells to that external AAS. Bundled BaSyx and AASX import/administration remain Full-mode features.

### External AAS server

Set `BASYX_AAS_URL` to use a provider-managed BaSyx or another compatible AAS REST server instead of the bundled service. External URLs must use `https://`, have an exact hostname in `AAS_ALLOWED_HOSTS`, and be protected with a dedicated `AAS_SERVICE_TOKEN` (optionally under `AAS_SERVICE_TOKEN_HEADER`). The Gateway strips caller JWTs before proxying and injects only this service credential. The same provider-side sync endpoints remain in use. An empty value disables AAS synchronization cleanly.

## Provider workflows

### Choose an AAS source

The provider can use one of three modes:

1. Bundled BaSyx in the Full Gateway, enabled with the `aas` profile.
2. An external AAS server configured through `BASYX_AAS_URL`.
3. No AAS, leaving the rest of the Gateway unchanged.

Do not enable AAS only to make a resource executable. FMU execution continues through the FMU proxy/runtime path, and physical-lab access continues through the existing Gateway/Station flows.

### Manage AAS shells in Lab Manager

The Lab Manager Digital Twins panel supports generated shell synchronization.
The Full Gateway also supports importing a provider-prepared `.aasx` package.
For an FMU, the selected laboratory automatically supplies the operational `accessKey` and stable `labId`; the description is
taken from the FMU model description when available and otherwise from the
laboratory metadata. For a physical laboratory, the Gateway uses the host and
Lab Station heartbeat, while the registered description, documentation links,
and Terms of Use URL are reused automatically. No separate Documentation or
License fields are needed in this panel.

The same FMU synchronization endpoint works with the local development runner
when the bundled `aas` profile is active. Without that profile, the local
runner reports AAS as unavailable rather than silently claiming that a shell
was updated.

The Full Gateway exposes FMU and physical-laboratory AAS synchronization from
the `Digital Twins` tab in Lab Manager. The selector uses the stable `labId`
from the provider's laboratory inventory. FMUs are available directly from
that inventory. Physical laboratories are shown only when the provider
catalog's `accessKey` resolves through a Guacamole connection whose hostname
matches exactly one registered host. Ops Worker's common resolver performs
this calculation and exposes it to Lab Manager through
`GET /ops/api/lab-associations`; the browser does not repeat the
connection/host intersection. For an FMU, the corresponding operational
`accessKey` is resolved automatically; operators do not select or type it
separately.

![Lab Manager Digital Twins tab](images/lab-manager-digital-twins.png)

### Synchronize an FMU shell

Use the provider's `lab-manager` to run:

~~~text
POST /aas-admin/fmu/{accessKey}/sync
~~~

The endpoint is protected by the existing `lab_manager_access.lua` mechanism (admin header, cookie or token) and is not a public booking endpoint. It:

1. calls the internal FMU `describe` operation;
2. generates IDTA 02005 `SimulationModels` v1.1, IDTA 02003 `TechnicalData`
   v2.0.1, and the standard capability, interface, contact and documentation
   submodels;
3. maps Terms of Use and documentation to IDTA 02004 `HandoverDocumentation`
   and contact email to IDTA 02002 `ContactInformations`;
4. creates or replaces the shell and submodels in the configured AAS server.

The optional `labId` parameter lets the provider keep a stable AAS identity anchored to a resource ID rather than to an operational FMU `accessKey`. The endpoint returns a disabled result when AAS is intentionally not configured and an upstream error when the configured AAS server cannot be reached.

An optional GLB scene or complete Three.js application can be linked through
the shell's IDTA 02004 `HandoverDocumentation` `File`. See the
[FMU visual assets guide](aas-fmu-visual-assets.md) for import, validation
and runtime details.

### Synchronize a physical-lab shell

`ops-worker` is responsible for physical-lab shells because it already owns
heartbeat persistence, host information and operational telemetry:

~~~text
POST /aas-admin/lab/{labId}/sync
~~~

Heartbeat persistence best-effort synchronizes the TechnicalData submodel. The
Digital Twins **Sync AAS** action synchronizes the selected physical lab and
uses its registered metadata. Ops Worker uses one resolver backed by the
provider catalog in
`blockchain-services`: `labId → accessKey → Guacamole connection → hostname →
unique registered host`. The synchronization is deliberately selected by
`labId`; a host can have multiple Guacamole connections and is not a safe AAS
selection key. Neither generated physical path depends on `fmu-runner`.

### Import a provider-prepared AASX package

For a provider-prepared package, use:

~~~text
POST /aas-admin/aas/{labId}/sync
~~~

The package must contain the stable shell ID `urn:decentralabs:lab:{labId}`;
otherwise it is rejected because Marketplace could not discover the imported
shell for that laboratory. This endpoint is available with the local
development FMU runner when the `aas` profile is running.

After a successful import, the Gateway records the laboratory association,
resource IDs, filename, size, checksum and timestamps in its local catalog.
It does not retain the uploaded archive. A later download is serialized from
the current shell and submodels in the configured AAS server, so it includes
subsequent server-side updates.

### Link an existing external AAS

When the provider already owns a shell elsewhere, it can link any laboratory
resource to that shell instead of generating a new one:

~~~text
POST   /aas-admin/lab/{labId}/aas-link
GET    /aas-admin/lab/{labId}/aas-link
DELETE /aas-admin/lab/{labId}/aas-link
GET    /aas-admin/resolve-aas-id?shellId=<shell-id>
~~~

The Gateway keeps the Marketplace-facing stable shell ID and resolves it to
the linked external AAS. The link is managed from the lab-manager **Link
Existing AAS** panel using only the laboratory ID. The old FMU access-key
routes remain available for existing FMU integrations, but new UI operations
are keyed by `labId`.

The Lab Manager's **AAS Associations** list combines three sources:
`Generated` shells discovered in the configured AAS server after synchronization,
`Imported` shells
registered after a successful AASX import, and `Linked` shells resolved through
external-link records. For imported shells, the Gateway keeps package
provenance in its local catalog but does not retain the uploaded archive.
Generated and imported entries can be deleted from the configured AAS
server; deleting a linked entry removes only the local link and never deletes
the externally managed shell.

### Keep the AAS identity stable

The stable shell identity is:

~~~text
urn:decentralabs:lab:{labId}
~~~

`accessKey` is operational and versioned. If the FMU changes but its resource identity remains the same, re-sync the existing shell without changing its AAS ID. A resource-type change is restricted by the on-chain resource/listing policy and must not silently turn a published resource into another type.

## Generated AAS content

### IDTA templates used by generated shells

Generated payloads use published [IDTA submodel templates](https://github.com/admin-shell-io/submodel-templates):

- [02005 Provision of Simulation Models](https://industrialdigitaltwin.org/wp-content/uploads/2026/03/IDTA-02005_Template_ProvisionOfSimulationModel.pdf)
- [02006 Digital Nameplate](https://industrialdigitaltwin.org/en/wp-content/uploads/sites/2/2024/11/IDTA-02006-3-0_Submodel_Digital-Nameplate.pdf)
- [02003 Generic Technical Data](https://industrialdigitaltwin.org/en/wp-content/uploads/sites/2/2025/03/IDTA-02003_Generic-Frame-for-Technical-Data.pdf)
- [02017 Asset Interfaces Description](https://github.com/admin-shell-io/submodel-templates)
- [02020 Capability Description](https://github.com/admin-shell-io/submodel-templates)
- [02002 Contact Information](https://industrialdigitaltwin.org/wp-content/uploads/2022/10/IDTA-02002-1-0_Submodel_ContactInformation.pdf)
- [02004 Handover Documentation](https://github.com/admin-shell-io/submodel-templates)

No `decentralabs.io/aas/...` semantic IDs are generated for these templates.

The main generated submodels vary by resource type:

| Resource | Main submodels | Typical information |
| --- | --- | --- |
| FMU simulation | IDTA 02005 `SimulationModels`, IDTA 02020 `CapabilityDescription`, IDTA 02017 `AssetInterfacesDescription`, IDTA 02003 `TechnicalData`, IDTA 02002/02004, DecentraLabs `FmiLsRelatedResources` when REF is present | Summary, FMI file type/version, ports, tools, solver values, model-file hash, runner status, discoverable execution affordances and a public index of embedded FMI-LS-REF resources. |
| Physical laboratory | IDTA 02006 `Nameplate`, IDTA 02020 `CapabilityDescription`, IDTA 02017 `AssetInterfacesDescription`, IDTA 02003 `TechnicalData`, IDTA 02002/02004 | Standard identity, host/network details as permitted arbitrary nameplate properties, heartbeat, station state and discoverable access/status affordances. |

The FMU `SimulationModels` submodel currently includes:

- standard `Ports` / `PortsConnector` / `Variable` elements mapped from FMI variables;
- `ModelFileType`, `ModelFileVersion` and the nested standard `DigitalFile` with SHA-256 integrity data;
- standard simulation-tool, solver/tolerance and `DefaultSimTime` elements;
- standard `LicenseModel`, manufacturer information, FMI capability properties and model display name; and
- units in the standard simulation-variable fields. The former custom
  `UnitDefinitions` submodel is no longer emitted.

The generated `CapabilityDescription` and `AssetInterfacesDescription`
submodels are intentionally separate from `SimulationModels` and
`TechnicalData`. They describe capabilities and affordances, not live status
and not authorization grants.

### FMI-LS-REF related resources

When the FMU contains a valid FMI-LS-REF manifest, generated synchronization
adds `FmiLsRelatedResources` with semantic ID
`urn:decentralabs:aas:FmiLsRelatedResources:1`. It projects the manifest name
and version plus each safe relative `Related` entry's role, media type, source
URI, description, labels and whether the referenced file exists in the FMU.
Absolute/external URIs are omitted so provider-private endpoints and credentials
are not copied into the public shell. File contents and parameter values are
not copied; FMI-LS-REF parameter presets continue to be read from the FMU by the
reservation-authorized simulation API. The whole projection is regenerated
from the current FMU on synchronization.

`HandoverDocumentation` continues to expose the selected visual asset through
its standard `File` element. That value is the Gateway-managed immutable asset
path used by Marketplace; it is a delivery reference, not a second copy of the
GLB or webapp ZIP. The related-resources submodel complements that viewer link
with a discoverable inventory of all embedded REF files, including alternative
visuals and parameter-set descriptors.

### Automatic versus manual data

| Resource | Filled automatically during generated sync | Still manual or provider-specific |
| --- | --- | --- |
| FMU | FMI model description, file type/version, ports, solver/tool metadata, model hash, capability names and endpoint affordance paths; contact/documentation submodels are generated from registered metadata. | Absolute deployment base URL, reservation policy, session-ticket issuance and any capability/operation semantics not covered by IDTA/WoT. |
| Physical laboratory | Resolved host, standard Digital Nameplate identity, heartbeat projection, standard capability names, interface affordances, contact and documentation links. | Instrument/actuator semantics, detailed station protocol, absolute deployment base URL and provider procedures. |

Generated synchronization emits `TechnicalData` for both resource types. An
imported provider-prepared `.aasx` package is not augmented with that generated
projection; if its shell should expose equivalent technical and runtime data,
the provider must include the appropriate submodel in the package.

Both generated resource types use IDTA 02003 `TechnicalData` with the same
stable submodel identifier. Runtime status/capacity is placed in the template's
official `TechnicalPropertyAreas` arbitrary-property extension because IDTA
02003 does not define a universal vocabulary for Gateway-specific health and
reservation projections. It is synchronized metadata, not a replacement for
Marketplace reservation state or live booking authorization.

The SHA-256 value is retained as a generic AAS metamodel `Extension` on the
standard FMU `File`, because IDTA 02005 has no checksum element. It is the only
generated integrity extension; it is not a DecentraLabs semantic vocabulary.

The generators target the published IDTA templates as far as the available
metadata allows. Provider-specific runtime and session details remain clearly
isolated in the standard arbitrary-extension slots. Conformance is not a
substitute for provider validation of the actual model and license metadata.

### FMI metadata for generated GLB controls

IDTA 02005 standardizes a port variable's name, range, type family,
description, unit and causality. It does not define FMI-specific fields such as
the exact FMI type, value reference, variability, initial attribute, start
value, nominal, display-unit conversion, vector dimensions or enumeration
items. Generated FMU shells keep the IDTA fields in their standard locations
and add only those missing FMI details to a versioned AAS `Extension` on each
port variable (`decentralabs.fmi.variableMetadata.v1`). This is a compact
metadata projection; it does not copy the FMU binary or create a second
manifest. The generator reads the model description used by the active FMU
backend, including Lab Station's description of the same FMU.

The Marketplace GLB route reads these AAS ports for control labels, types,
units, ranges, defaults, dimensions and enumeration choices. It checks each
variable against the FMU description that governs simulation requests. Missing
AAS fields are filled from that description; a conflicting name, causality,
type, bound, default or unit falls back to FMU metadata. AAS descriptions and
display names remain presentation metadata. The FMU description is still the
authority for execution and validation. External or older AAS shells without
the extension continue to work through standard fields and FMU fallback.

## FMI variable access policy

Generated FMU synchronization creates an initial variable access policy from
the active FMU's `modelDescription.xml`; providers do not need to enter a rule
for every port. FMI remains the source for variable names, causalities,
variability, types and supported write phases. The AAS stores only the access
rules and a digest of the FMI interface to which those rules apply.

The Gateway stores the rules as an `application/json` Blob containing the
IDTA 01004 Part 4 `AllAccessPermissionRules` structure in a separate
`SimulationAccessControl` submodel referenced by the AAS shell. OpenResty
blocks direct retrieval of generated policy submodels and explicit inclusion
in public AAS serialization queries. The private Gateway resolver reads the
policy from the configured AAS server using provider-side configuration. Its
cache is bounded to five seconds and is invalidated when AAS synchronization or linking changes the
association.

The current DecentraLabs profile is based on the IDTA 01004 v3.1 JSON
serialization and accepts exact `REFERABLE` objects for
`SimulationModels/Ports`, `READ` and `UPDATE` `ALLOW` rules, reusable Part 4
`DEFATTRIBUTES`, `DEFACLS`, `DEFOBJECTS` and `DEFFORMULAS` definitions with
their `USE...` references, and boolean/equality formulas over authenticated
scalar claims (`$boolean`, `$eq`, `$ne`, `$and`, and `$or`). ACLs may use inline
attributes and/or reusable attribute groups; rule objects may combine inline
referables with reusable object groups. Attribute and object groups can refer
to other groups, subject to cycle, depth, expansion and size limits. An
explicit `ACCESS: DISABLED` rule is ignored as Part 4 defines. Unsupported
object kinds, rights, filters, formula operators and malformed definitions are
rejected. The compiler also fails closed on unknown variables or paths, stale
interface digests, and any rule that grants more than the FMI/runtime supports.
A provider can author a supported policy through AAS administration tooling or
include it in an imported FMU AASX package. Lab Manager shows policy status and
allows explicit regeneration of FMI defaults;
regeneration replaces provider edits and therefore requires confirmation. FMU
AASX imports preserve and validate one supported policy or create the initial
default policy when one is missing. The Gateway does not modify a linked
external AAS; it can consume the supported restricted Part 4 JSON profile when
the provider has linked it. The Part 4 `UPDATE` right covers the write phases
supported for that variable by FMI and the runtime; FMI 2.0 and FMI 3.0
Co-Simulation `tunable` parameters can be changed at initialization and at
runtime communication points. The Lab Manager link panel checks FMU AAS links
and displays a warning when the linked shell, policy submodel or
policy-to-FMU mapping cannot be validated. An external AAS with no compatible
policy uses FMI-derived defaults and is reported as such; the status check
never edits the external shell.

The table separates FMI causality, the IDTA 02005 port description and the
default Part 4 access rights. Port groups and `VariableCausality` describe a
variable's kind or direction; they are not privacy permissions. Privacy is
represented separately by IDTA 01004 Part 4 `READ` and `UPDATE` rules in
`SimulationAccessControl`. The Gateway derives write phases from the active
FMU metadata and runtime capabilities.

| FMI causality | IDTA 02005 port description | Generated Part 4 rights |
| --- | --- | --- |
| `input` | `Input` / `Input` | `READ`; `UPDATE` when variability is recognized. |
| `output` | `Output` / `Output` | `READ`. |
| `parameter` | `Parameter` / `Input` | `READ`; `UPDATE` for `fixed` or `tunable` variability. |
| `calculatedParameter` | `Parameter` / `Input` | `READ`; read-only. |
| `structuralParameter` | `Parameter` / `Input` | `READ`; writes are unavailable in the current runtime contract. |
| `independent` | `Internal` / `Acausal` | `READ`; read-only. |
| `local` | Omitted from generated `Ports` | No access rule. |
| Unknown causality | `Internal` / `Acausal`, if present | No access; fails closed. |

Default write phases are:

- **Inputs:** initialization when variability is recognized; runtime for
  `continuous`, `discrete` and `tunable` inputs. `constant` and `fixed` inputs
  are therefore initialization-only.
- **Parameters:** initialization for `fixed` and `tunable`; runtime
  communication points for `tunable` parameters in FMI 2.0/3.0 Co-Simulation.

Read access is granted by default for recognized non-`local` causalities. An
unrecognized variability preserves default read access but grants no write
permission; an unrecognized causality grants neither read nor write access.
Provider-authored AAS rules may restrict these defaults, but cannot grant
access beyond FMI and runtime support.

The effective decision is enforced by Gateway for run, stream, job/batch,
result/history and Station WebSocket paths. Denied writes are rejected before
forwarding; unreadable values are filtered from results and session messages.
The realtime session accepts reads by variable name or FMI `valueReference`;
numeric references are resolved against the authorized FMU description before
the Gateway forwards the request.
The reservation-bound proxy FMU and `describe` response expose only permitted
variables, and hide `start` when a variable is writeable but not readable. The
protected `GET /fmu/api/v1/simulations/access` endpoint returns the effective
permissions and authorized variable metadata. Marketplace calls this through
its same-origin `POST /api/simulations/access` route and uses the result to
filter the standard form, GLB viewer, results and Three.js app metadata. The
Gateway remains the enforcement point if a client ignores the UI contract.
Active Station WebSocket sessions refresh the policy before forwarding commands
or returning FMI data; the five-second resolver cache bounds how quickly an
AAS policy edit becomes effective. The Gateway pins the trusted FMI interface
metadata read for that active FMU session and reuses it when re-evaluating the
policy, so each WebSocket frame does not trigger another FMU metadata read.
The pinned metadata remains server-side and is never accepted from the browser.

This policy governs simulation operations and runtime values. Static interface
descriptions in public lab metadata and `SimulationModels/Ports` may still be
visible, including names, ranges and descriptions; it does not make those
descriptors confidential or retract metadata already published on-chain. That
privacy boundary needs a separate design if providers need to hide static
metadata as well as simulation values. No reservation key, JWT, session ticket
or service credential is stored in the AAS policy.

## Consumer guide

### Marketplace behavior

Marketplace requests the provider shell through a server-side route with SSRF protection and rate limiting. The resource page shows an AAS panel only when the provider Gateway returns a shell. A 404 or unavailable optional AAS server leaves the normal resource page unchanged.

When available, the panel can show:

- asset type and stable AAS ID;
- resolved host and last synchronization information;
- operational status, readiness, backend/session capacity and heartbeat when
  the provider publishes `TechnicalData`;
- FMU description, license, documentation links and contact; and
- the capability names and interface affordances when the provider publishes
  `CapabilityDescription` and `AssetInterfacesDescription`; and
- a link to the raw shell or a downloadable `.aasx` package.

AAS metadata helps a consumer understand and compare a resource. It does not replace authentication, a reservation, a session ticket, a physical-lab access token or the FMI proxy authorization flow.

### How to interpret an FMU AAS

Use `SimulationModels` to inspect the model's summary, exposed ports, causality, supported tools, capabilities, units, tolerance and license. Use `TechnicalData` for the last known runner status and capacity; it is not a live reservation guarantee. Then verify that the Marketplace listing and reservation conditions match the intended use. A shell is provider-published metadata; the consumer should not assume that an AAS property alone grants execution rights.

### How to interpret a physical-lab AAS

Use Nameplate and TechnicalData to understand the identity and last known operational description of the lab. Live availability and reservation state still come from Marketplace and the control plane, not from a cached AAS shell.

## Security and routing

OpenResty separates public read access from provider administration:

~~~text
/aas/                -> BaSyx or BASYX_AAS_URL
/aas-admin/fmu/      -> fmu-runner
/aas-admin/aas/      -> fmu-runner (unified AAS association administration)
/aas-admin/lab/      -> ops-worker
~~~

The administration routes require `LAB_MANAGER_TOKEN` through the shared lab-manager access guard, even when the Gateway is reachable from a private network. AAS write operations must not reuse public booking/JWT endpoints.

The provider should also:

- protect the AAS server and admin routes with the Gateway network policy; the bundled profile keeps BaSyx/Mongo on the internal `fmu_aas`/`fmu_aas_ops`/`aas_data` networks, with separate AAS edges for the FMU and Ops services, and enables Mongo authentication;
- configure an exact `AAS_ALLOWED_HOSTS` entry and dedicated `AAS_SERVICE_TOKEN` for every external AAS endpoint; caller JWTs are stripped at the Gateway;
- avoid putting secrets or bearer tokens in shell properties;
- validate and sanitize external URLs, especially documentation and AAS link targets;
- keep AAS data and BaSyx storage backed up according to provider policy; and
- treat license and contact fields as published metadata visible to consumers.

## AASX import limits and validation

Provider AASX imports are resource-bounded: 50 MiB compressed, 256 MiB total
expanded ZIP content, at most 10,000 entries, at most 16 MiB for the AAS
environment part, and 1 MiB per OPC relationships part. XML DTD and entity
declarations are not accepted. These limits apply before imported resources are
synchronized to the configured AAS server.

Development checks use the Eclipse BaSyx Python SDK 2.1.0 as an independent
AAS/AASX reader. They parse generated JSON and round-trip generated packages
with `failsafe=False`, so invalid metamodel fields, typed values, XML or
OPC/AASX relationships are reported instead of being silently skipped.

To validate a downloaded package manually from `fmu-runner`:

~~~bash
python tools/validate_aasx.py path/to/lab.aasx
~~~

This checks generic AAS metamodel/AASX validity. IDTA template semantics and
provider-specific operational meaning remain covered by the generator tests and
semantic IDs; they cannot be inferred solely from the AASX container parser.

## Implementation status

Implemented in the Gateway ecosystem:

- optional bundled BaSyx service for Full Gateway deployments;
- external AAS server selection through `BASYX_AAS_URL`;
- FMU shell generation and `.aasx` ingestion in `fmu-runner`;
- physical-lab Nameplate and TechnicalData generation in `ops-worker`;
- unified Lab Manager synchronization for FMUs and physical laboratories;
- provider-prepared AASX import for any laboratory resource;
- Marketplace shell discovery, AAS panel and AASX download from the configured provider AAS server;
- unified Lab Manager associations for generated, imported and externally linked AAS shells;
- transparent links to existing external AAS shells;
- IDTA 02005 simulation-model mapping including FMI ports, units and integrity metadata;
- IDTA 02003/02006 technical-data and nameplate mapping;
- IDTA 02020 capability and IDTA 02017 interface descriptions for generated FMUs and physical laboratories, without embedding credentials or changing the protected runtime paths; and
- an initial FMI variable access profile generated from FMU metadata, enforced by the Gateway on simulation operations and consumed by the Marketplace viewer.

The following remain future work:

- a Lab Manager editor for detailed provider-authored rules and broader interoperability with arbitrary Part 4 policy submodels;
- multi-Gateway AAS federation and cross-provider shell aggregation;
- on-chain registration and verification of AAS IDs; and
- Verifiable Credentials/DIDs attached to AAS licensing or provenance data.

These items are not prerequisites for the current AAS MVP. Shell generation, publication and discovery work independently of blockchain; existing provider identity and Gateway resolution controls remain the security boundary.

## Acceptance checklist

Use this checklist when connecting AAS metadata to a provider resource or
validating the consumer flow.

### Provider

- [ ] Decide bundled, external or disabled AAS mode.
- [ ] Keep the Full/Lite deployment distinction explicit.
- [ ] Synchronize FMU shells from `lab-manager` or ingest a validated `.aasx`.
- [ ] Verify the stable `labId`-anchored AAS ID and operational `accessKey`.
- [ ] Add only metadata intended for consumer visibility.
- [ ] Confirm the AAS server is persistent and backed up.
- [ ] Test shell retrieval through the provider Gateway, not only directly against the AAS server.

### Consumer

- [ ] Treat AAS as descriptive metadata, not an access credential.
- [ ] Check the model's ports, capabilities, tools, units and license.
- [ ] Treat described execution/access operations as an interoperability contract, not as directly invokable AAS commands.
- [ ] Check physical-lab technical data separately from live availability.
- [ ] Follow the normal Marketplace reservation and access flow.
- [ ] Use raw JSON/AASX only as an additional integration artifact and validate it against the provider's published terms.
