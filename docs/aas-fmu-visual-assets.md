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
continue to work when it is omitted or AAS is unavailable. Lab Manager defaults
to automatic discovery. It reads local visual assets declared in the
FMI-LS-REF manifest at
`extra/org.fmi-standard.fmi-ls-ref/fmi-ls-manifest.xml`. A Three.js webapp ZIP
is preferred whenever one is declared or available as the same-stem
`{model}.webapp.zip`; otherwise Gateway uses a declared GLB, then a same-stem
`{model}.glb`. If neither exists, the provider can continue without a visual
asset or upload one. The provider can still select a specific asset type. A
public HTTPS URL is supported for GLB scenes only.

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
files and unsafe paths are rejected. Apps may include HTTPS links for user
navigation, while scripts, styles and other loaded assets must stay bundled.
Gateway executes no provider server code.

The authenticated Gateway import endpoint is
`POST /lab-admin/digital-twin-assets/{labId}/from-fmu` with JSON
`{"accessKey":"...","assetType":"auto|glb|threejs-app"}`. Auto returns the
resolved `assetType` and whether it came from `fmi-ls-ref` or a legacy same-stem
companion. A direct upload uses
`PUT /lab-admin/digital-twin-assets/{labId}` with `model/gltf-binary` or
`application/zip`.

## Validation and scene bindings

For a GLB upload or FMU companion import, Gateway compares each
`extras.fmiBindings` entry with the selected FMU's declared inputs or outputs
and the targets supported by Marketplace. Input bindings are accepted for
numeric inputs mapped to a position axis with a finite, non-zero scale. The
response includes a transient `validation` report with binding counts and any
findings; it is derived from the FMU and GLB and is not stored in the AAS. A scene with warnings can
still be stored, but Lab Manager shows the findings and asks the provider to
review them before synchronizing. Public HTTPS GLBs cannot be inspected by
Gateway and are labelled unchecked. Three.js ZIP validation checks the
package structure and bundled paths; Marketplace checks the app's startup
handshake when it is opened.

For an FMU-driven GLB scene, the provider authors `extras.fmiBindings` on nodes
that represent relevant FMU outputs or writable numeric inputs. Output bindings
drive scene targets from model samples. An input binding to `position.x`,
`position.y` or `position.z` also enables constrained dragging in Marketplace;
the existing `scale` and `offset` map between the input value and the node's
local position. Each node can have only one binding per position axis for
unambiguous dragging; the Gateway reports an input binding that shares its
position target with another binding. FMI minimum and maximum values constrain
the drag. Scene dragging is available only during live Step by step or
Continuous execution when Gateway permits runtime writes; initialization values
remain editable through the standard input controls. A GLB without bindings may render as static
geometry, but it cannot behave as an FMU-driven digital twin.

See the [DecentraLabs FMI GLB bindings contract](https://github.com/DecentraLabsCom/Marketplace/blob/main/docs/provider/fmi-glb-bindings-contract.md)
for the canonical versioned specification, target semantics, examples and JSON
Schema.

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
and generated interfaces retain their Marketplace execution path. Generated
GLB viewers use the batch stream for scheduled runs. For reserved FMI 2/3
Co-Simulation models, step-by-step and continuous live modes request the same
reservation-scoped connection grant used by provider apps, then open the
Gateway session WebSocket from the Marketplace page. Step mode sends one
`sim.step` request per user action. Continuous mode uses `sim.advance` to
request bounded batches of intermediate samples, starting at one communication
sample and adapting up to the lower of 256 samples or 2% of the configured
model-time horizon, rounded down to whole communication steps with a one-step
minimum. This unit-independent limit preserves roughly 50 communication
opportunities across runs with at least 50 configured steps. The viewer adjusts
the next batch using smoothed request
response time and the delay until the latest sample is rendered. During
interactive execution, the GLB viewer follows the latest sample and retains the
full timeline for replay after the run. Runtime edits are sent before the next
batch, after the current advance completes. The Gateway enforces its effective
variable-access policy on every write and filters output values returned to the
browser. The page's exact
origin must be allowed by the Gateway's `MARKETPLACE_URL` or
`CORS_ALLOWED_ORIGINS` configuration, and the Marketplace operator must include
this Gateway's WSS origin in `CSP_CONNECT_SRC` so its browser policy permits the
direct session connection.
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
    alt Batch
        U->>M: Set inputs and schedule changes
        M->>G: POST /fmu/api/v1/simulations/stream with reservation authorization
        G->>S: Forward execution through the private Station connection
        S-->>G: Stream FMU output samples
        G-->>M: Return output stream
        M->>M: Apply output values using GLB extras.fmiBindings
        M-->>U: Update the scene, timeline and output indicators
    else Step by step or continuous live
        U->>M: Select mode and set initial inputs
        M->>G: POST /fmu/api/v1/fmu/connection/{labId}
        G-->>M: Return reservation-scoped connection grant
        M-->>U: Provide temporary grant
        U->>G: WSS session.create
        G->>S: Open private realtime session
        alt Step by step
            U->>G: sim.initialize with external time mode
            loop One step per click
                U->>G: Optional sim.setInputs, then sim.step
                G->>S: Forward authorized session messages
                S-->>G: Return current simulation outputs
                G-->>U: Filtered output sample
                U->>U: Update GLB bindings, timeline and indicators
            end
        else Continuous live
            U->>G: sim.initialize with simulation time mode
            loop Adaptive batch
                U->>G: Optional sim.setInputs, then sim.advance
                G->>S: Forward authorized session messages
                S-->>G: Return bounded intermediate samples
                G-->>U: Filtered sample batch
                U->>U: Append samples and update the displayed scene
            end
        end
    end
    Note over M,S: Batch samples pass through Marketplace. Interactive steps and samples travel directly between the browser and Gateway.
~~~

## AASX and public GLB constraints

The AAS File stores the visual asset location and MIME type only. FMI remains the
source of model execution; the generated GLB interface reads its variable
descriptions from AAS `SimulationModels` ports when present. Provider-authored
GLB `extras.fmiBindings` map FMI input and output names to allowed scene targets
and are required for output-driven or input-interactive scene behavior, while a
Three.js app owns its rendering logic. No additional GLB-specific manifest is
used; an FMU can separately declare the asset as a related file in
FMI-LS-REF. When
uploading an `.aasx`
package, its Handover Documentation remains authoritative
and cannot be combined with a separate visual-asset upload. Public HTTPS GLB
URLs must allow browser CORS, use an origin permitted by Marketplace
`CSP_CONNECT_SRC`, and contain no credentials or access tokens.

Generated AAS shells also include a `FmiLsRelatedResources` submodel when the
FMU declares embedded resources in FMI-LS-REF. It records descriptors for all
declared local resources, while `HandoverDocumentation` points to the visual
asset selected by the Gateway. Neither submodel copies the GLB or webapp ZIP
bytes into AASX by itself.
