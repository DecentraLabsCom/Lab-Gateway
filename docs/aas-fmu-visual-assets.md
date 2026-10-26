# FMU Visual Assets Linked Through AAS

An FMU AAS shell can reference an optional GLB scene or a complete Three.js application. The AAS stores the asset reference and MIME type; the Gateway stores and serves the static asset. Marketplace selects the viewer from that reference. This guide covers the provider asset workflow and runtime path; the Three.js message contract is documented by Marketplace.

## Contents

- [Link an asset through AAS](#link-an-asset-through-aas)
- [AAS reference and viewer selection](#aas-reference-and-viewer-selection)
- [Gateway storage and endpoints](#gateway-storage-and-endpoints)
- [Validation and scene bindings](#validation-and-scene-bindings)
- [Marketplace runtime flow](#marketplace-runtime-flow)
- [AASX and public GLB constraints](#aasx-and-public-glb-constraints)

## Link an asset through AAS

To link an optional visual asset, set `digitalTwinAssetUrl` during generated
FMU sync. The generator stores it in the existing IDTA 02004
`HandoverDocumentation` as a `File`; its managed Gateway path determines the
MIME type and therefore Marketplace's viewer:

~~~text
POST /aas-admin/fmu/{accessKey}/sync?labId={labId}&digitalTwinAssetUrl={encoded-Gateway-asset-path}
~~~

The visual link is optional: FMU simulation and the standard results viewer
continue to work when it is omitted or AAS is unavailable. Lab Manager lets the
provider select no visual asset, a GLB, or a static Three.js application. The
provider can import a same-stem companion from the active FMU backend or upload
the asset. A public HTTPS URL is supported for GLB scenes only.

Smart Warehouse includes both a GLB scene and a companion Three.js application.
The canonical FMU, scene, app ZIP and license live in FMU-Executor; Gateway
development and Windows/Linux amd64 Station packages carry runtime copies
beside the platform-specific FMU. Linux arm64 omits this x86_64-only demo. In
production, Gateway imports the selected companion from Lab Station through
its token-protected internal endpoint. Station does not publish the asset
publicly.

## AAS reference and viewer selection

Generated FMU shells use the existing IDTA 02004 `HandoverDocumentation`
`File` as the single visual-asset link. Its `contentType` selects Marketplace's
renderer:

| File MIME | Gateway path | Marketplace presentation |
| --- | --- | --- |
| `model/gltf-binary` | `/digital-twin-scenes/{labId}/{sha256}.glb` | Generic Three.js GLB viewer; reads node `extras.fmiBindings` |
| `text/html` | `/digital-twin-apps/{labId}/{sha256}/index.html` | Provider's static Three.js app, sandboxed in an iframe |

## Gateway storage and endpoints

Gateway stores each managed asset read-only under an immutable,
content-addressed path. It accepts self-contained glTF 2.0 binary scenes up to
50 MiB. Static app ZIPs must contain a root `index.html`, use safe relative
asset paths and bundled modules, and stay within the configured file-count and
expanded-size limits. Assets are served as static files; there is no per-app
filename or file-format allowlist. Native executable files, symlinks, special
files and unsafe paths are rejected. Gateway executes no provider server code.

The authenticated Gateway import endpoint is
`POST /lab-admin/digital-twin-assets/{labId}/from-fmu` with JSON
`{"accessKey":"...","assetType":"glb|threejs-app"}`. A direct upload uses
`PUT /lab-admin/digital-twin-assets/{labId}` with `model/gltf-binary` or
`application/zip`.

## Validation and scene bindings

For a GLB upload or FMU companion import, Gateway compares each
`extras.fmiBindings` entry with the selected FMU's declared outputs and the
targets supported by Marketplace. The response includes a transient
`validation` report with the binding counts and any findings; it is derived
from the FMU and GLB and is not stored in the AAS. A scene with warnings can
still be stored, but Lab Manager shows the findings and asks the provider to
review them before synchronizing. Public HTTPS GLBs cannot be inspected by
Gateway and are labelled unchecked. Three.js ZIP validation checks the
package structure and bundled paths; Marketplace checks the app's startup
handshake when it is opened.

For an FMU-driven GLB scene, the provider must author the `extras.fmiBindings`
that connect its visual elements to the relevant FMU outputs. A GLB without
bindings may render as static geometry, but it cannot behave as an
output-driven digital twin.

## Marketplace runtime flow

Marketplace resolves either managed asset against the lab's on-chain Gateway
origin, then proxies only that lab's immutable scene or app files through
same-origin API routes. The GLB route accepts only the lab ID and its
content-addressed digest; it does not proxy arbitrary URLs. Gateway applies a
restrictive CSP sandbox to the public app route, and Marketplace serves the app
entry page in an isolated iframe with its own restrictive CSP and no
credentials. For a Three.js app, Marketplace's postMessage integration handles
iframe startup, the one-use connection grant and optional shared HMI controls.
The app opens the provider Gateway's FMU session WebSocket; FMU requests and
simulation samples travel directly between the app and Gateway, then to the
private Station Executor. Marketplace never relays simulation requests or
samples, and never sends the FMU, access key or reservation token. GLB scenes
and generated interfaces retain their existing Marketplace execution path.
This section documents the AAS asset reference and Gateway storage, validation
and delivery responsibilities; message names, payloads and lifecycle belong in
Marketplace's **Three.js digital twin app contract**. The app owns the complete
presentation inside its viewer area. Marketplace does not wrap it in the GLB
viewer or add that viewer's charts or output table, though it may show shared
input-schedule and capability-gated playback controls as overlays.

The GLB path keeps simulation execution in Marketplace's generated interface.
This sequence includes both the provider's asset setup and the consumer's
runtime flow:

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Provider in Lab Manager
    participant G as Provider Gateway
    participant A as Provider AAS
    participant U as Consumer browser
    participant M as Marketplace UI and API
    participant S as Lab Station FMU Executor
    P->>G: Upload or import GLB companion
    G->>G: Validate bindings and store immutable asset
    P->>G: Synchronize FMU shell with selected visual asset
    G->>A: Write HandoverDocumentation File reference and MIME type
    A-->>G: Shell synchronized
    U->>M: Open the reserved FMU lab
    M->>A: Read the lab's AAS shell
    A-->>M: Return GLB path and SimulationModels port metadata
    M->>M: Match AAS variables to the FMU description for generated controls
    M->>G: Fetch GLB through Marketplace's same-origin asset proxy
    G-->>M: Return immutable GLB file
    M-->>U: Render generated controls and GLB viewer
    U->>M: Set inputs and run simulation
    M->>G: POST /fmu/api/v1/simulations/stream with reservation authorization
    G->>S: Forward execution through the private Station connection
    S-->>G: Stream FMU output samples
    G-->>M: Return output stream
    M->>M: Apply output values using GLB extras.fmiBindings
    M-->>U: Update the scene, timeline and output indicators
    Note over M,S: The generated GLB route uses Marketplace's authorized simulation API; only complete Three.js apps open the direct session WebSocket.
~~~

## AASX and public GLB constraints

The AAS File stores the visual asset location and MIME type only. FMI remains the
source of model execution; the generated GLB interface reads its variable
descriptions from AAS `SimulationModels` ports when present. Provider-authored
GLB `extras.fmiBindings` map FMI output names to allowed scene targets and are
required for output-driven scene behavior, while a Three.js app owns its
rendering logic. No separate manifest is used. When uploading an `.aasx`
package, its Handover Documentation remains authoritative
and cannot be combined with a separate visual-asset upload. Public HTTPS GLB
URLs must allow browser CORS, use an origin permitted by Marketplace
`CSP_CONNECT_SRC`, and contain no credentials or access tokens.
