# DecentraLabs FMU Proxy Runtime Source

This directory contains the source implementation for the native runtime that
is packaged into generated `proxy.fmu` artifacts.

It is intentionally separate from `../fmu-proxy-runtime/`, which remains the
binary drop location mounted into `fmu-runner`.

## Current decisions

- Transport: `WSS` from proxy runtime to Gateway
- FMI target: `FMI 2.0.x Co-Simulation` for the MVP, with current `win64`
  support extended to scalar/dimensioned `FMI 3.0 Co-Simulation`
- Implementation language: `C++17` with a future C ABI export layer for FMI
- Artifact model: generic runtime binaries plus reservation-specific
  `modelDescription.xml` and `resources/config.json`

## Current implementation status

The files here now implement a functional `win64` runtime:

- FMI 2 Co-Simulation export layer
- FMI 3 Co-Simulation export layer for scalar and dimensioned variables
- widened FMI 3 primitive type support in the runtime source and ABI:
  `Float32`, `Float64`, `Int8`, `UInt8`, `Int16`, `UInt16`, `Int32`,
  `UInt32`, `Int64`, `UInt64`, `Boolean`, `String`, `Binary`, `Clock`
- `resources/config.json` loading
- `modelDescription.xml` parsing for generated proxy metadata
- local runtime state, cached values and FMI call mapping
- Gateway protocol client with request/response correlation
- native `WSS` transport on Windows via WinHTTP
- native `WSS` transport on Linux via OpenSSL + raw sockets/WebSocket framing
- native POSIX/OpenSSL `WSS` source path shared by Linux and Darwin
- loopback/self-signed TLS tolerance for local Gateway development
- a compiled `win64` DLL build in `build-win64/`
- a reproducible `linux64` build in `build-linux64/`
- end-to-end validation against the live Lab Gateway stack with `fmpy`
  for both:
  - FMI 2 proxy generation/loading
  - FMI 3 scalar proxy generation/loading (`Stair.fmu`)
  - FMI 3 dimensioned-variable proxy generation/loading (`StateSpace.fmu`)
  - Linux-container loading of downloaded `proxy.fmu` artifacts for:
    - FMI 2 (`BouncingBall.fmu`)
    - FMI 3 with dimensioned outputs (`StateSpace.fmu`)

What still is not finished:

- `darwin64` is prepared at source/build level, but no real binary has been built yet
- `darwin64` is not validated end-to-end yet
- `Binary` and `Clock` are now implemented in the proxy generator, local Gateway path and runtime ABI, but they are not yet validated against a real sample FMU/tool pair in this environment
- full-range exact `Int64` / `UInt64` fidelity is preserved in the current Gateway/runtime path by transporting 64-bit integers as decimal strings where required
- FMI 3 support is still not validated across the full type matrix and tool matrix
- FMI 3 Model Exchange and Scheduled Execution are not supported

The future compiled binaries produced by this project are expected to be copied
into:

- `../fmu-proxy-runtime/binaries/linux64/decentralabs_proxy.so`
- `../fmu-proxy-runtime/binaries/win64/decentralabs_proxy.dll`
- `../fmu-proxy-runtime/binaries/darwin64/decentralabs_proxy.dylib`

## Reproducible linux64 build

From Windows with Docker Desktop running:

```powershell
pwsh .\fmu-proxy-runtime-src\build-linux64-runtime.ps1

# Build and promote the shared library to the runtime drop path
pwsh .\fmu-proxy-runtime-src\build-linux64-runtime.ps1 -Promote
```

This uses `docker/linux64-builder.Dockerfile` and produces:

- `build-linux64/libdecentralabs_proxy.so`
- optionally `../fmu-proxy-runtime/binaries/linux64/decentralabs_proxy.so`

## Native darwin64 build

Run this on a real macOS machine with Xcode Command Line Tools, CMake, Ninja and OpenSSL 3 installed:

```bash
cd fmu-proxy-runtime-src
./build-darwin64-runtime.sh

# Build and promote the dylib to the runtime drop path
./build-darwin64-runtime.sh --promote
```

By default the script looks for OpenSSL at `OPENSSL_ROOT_DIR` and then falls back to `brew --prefix openssl@3`.

## Project layout

```text
fmu-proxy-runtime-src/
|- ARCHITECTURE.md
|- CMakeLists.txt
|- include/decentralabs_proxy/
|  |- protocol.hpp
|  |- runtime_config.hpp
|  |- runtime.hpp
|  |- transport.hpp
|  `- session_state.hpp
`- src/
   |- fmi2_exports.cpp
   |- gateway_client.cpp
   |- json.cpp
   |- model_description.cpp
   |- protocol.cpp
   |- runtime.cpp
   |- runtime_config.cpp
   |- session_state.cpp
   |- transport.cpp
   `- transport_linux.cpp
```

## Next milestones

1. Produce and validate a real `darwin64` binary
2. Add dedicated automated regression coverage for FMI 2 and FMI 3 live proxy simulation
3. Validate `Binary` and `Clock` against real FMI 3 sample FMUs and tools
4. Extend FMI 3 support to Model Exchange and Scheduled Execution
5. Validate the exact `Int64` / `UInt64` transport path against more external FMI tools
