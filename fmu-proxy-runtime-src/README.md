# DecentraLabs FMU Proxy Runtime Source

This directory contains the source implementation for the native runtime that
is packaged into generated `proxy.fmu` artifacts.

It is intentionally separate from `../fmu-proxy-runtime/`, which remains the
binary drop location mounted into `fmu-runner`.

## Current decisions

- Transport: `WSS` from proxy runtime to Gateway
- FMI target: `FMI 2.0.x Co-Simulation` for the MVP, with current `win64`
  support extended to scalar `FMI 3.0 Co-Simulation`
- Implementation language: `C++17` with a future C ABI export layer for FMI
- Artifact model: generic runtime binaries plus reservation-specific
  `modelDescription.xml` and `resources/config.json`

## Current implementation status

The files here now implement a functional `win64` runtime:

- FMI 2 Co-Simulation export layer
- FMI 3 scalar Co-Simulation export layer
- FMI 3 dimensioned variable support for the `win64` runtime
- `resources/config.json` loading
- `modelDescription.xml` parsing for generated proxy metadata
- local runtime state, cached values and FMI call mapping
- Gateway protocol client with request/response correlation
- native `WSS` transport on Windows via WinHTTP
- loopback/self-signed TLS tolerance for local Gateway development
- a compiled `win64` DLL build in `build-win64/`
- end-to-end validation against the live Lab Gateway stack with `fmpy`
  for both:
  - FMI 2 proxy generation/loading
  - FMI 3 scalar proxy generation/loading (`Stair.fmu`)
  - FMI 3 dimensioned-variable proxy generation/loading (`StateSpace.fmu`)

What still is not finished:

- `linux64` and `darwin64` binaries are not built yet
- non-Windows transports still fall back to the stub transport
- FMI 3 support is still not validated across the full type matrix and tool matrix
- FMI 3 Model Exchange and Scheduled Execution are not supported

The future compiled binaries produced by this project are expected to be copied
into:

- `../fmu-proxy-runtime/binaries/linux64/decentralabs_proxy.so`
- `../fmu-proxy-runtime/binaries/win64/decentralabs_proxy.dll`
- `../fmu-proxy-runtime/binaries/darwin64/decentralabs_proxy.dylib`

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
   `- transport.cpp
```

## Next milestones

1. Produce `linux64` and `darwin64` binaries
2. Decide whether non-Windows transports also use native platform APIs or a shared dependency
3. Add dedicated automated regression coverage for FMI 2 and FMI 3 live proxy simulation
4. Promote the compiled artifacts into `../fmu-proxy-runtime/binaries/...`
