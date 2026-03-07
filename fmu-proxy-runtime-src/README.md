# DecentraLabs FMU Proxy Runtime Source

This directory contains the source scaffold and implementation plan for the
native runtime that will be packaged into generated `proxy.fmu` artifacts.

It is intentionally separate from `../fmu-proxy-runtime/`, which remains the
binary drop location mounted into `fmu-runner`.

## Current decisions

- Transport: `WSS` from proxy runtime to Gateway
- FMI target: `FMI 2.0.x Co-Simulation` for the MVP
- Implementation language: `C++17` with a future C ABI export layer for FMI
- Artifact model: generic runtime binaries plus reservation-specific
  `modelDescription.xml` and `resources/config.json`

## Scope of this scaffold

The files here do not yet implement a functional FMU runtime. They establish:

- project layout
- core runtime configuration model
- protocol message inventory
- session lifecycle model
- implementation roadmap

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
|  `- session_state.hpp
`- src/
   |- protocol.cpp
   |- runtime_config.cpp
   `- session_state.cpp
```

## Next milestones

1. Add the FMI 2 C export layer (`fmi2Instantiate`, `fmi2DoStep`, `fmi2Get*`, ...)
2. Parse `resources/config.json` from the extracted FMU resources directory
3. Implement a WSS transport adapter
4. Map FMI calls to the existing Gateway protocol
5. Produce signed multi-platform binaries for `fmu-proxy-runtime/`
