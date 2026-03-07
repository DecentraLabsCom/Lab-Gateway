# FMU Proxy Runtime

This directory is mounted into `fmu-runner` as `/app/fmu-proxy-runtime`.

The proxy download endpoint only works when the FMI proxy runtime binaries are present under:

```text
fmu-proxy-runtime/
└── binaries/
    ├── linux64/
    ├── win64/
    └── darwin64/
```

Expected contents are the real proxy runtime binaries for each target platform, for example:

- `binaries/linux64/decentralabs_proxy.so`
- `binaries/win64/decentralabs_proxy.dll`
- `binaries/darwin64/decentralabs_proxy.dylib`

Notes:

- `.gitkeep` files are intentionally ignored by `fmu-runner` and do not count as provisioned runtime files.
- If the platform binaries are missing, `GET /api/v1/fmu/proxy/{labId}` will return `503 FMU proxy runtime binaries are not provisioned on Lab Gateway`.
- The native source scaffold and implementation plan now live in `../fmu-proxy-runtime-src/`.
- `fmu-runner` should keep reading binaries from this directory only; build outputs from `../fmu-proxy-runtime-src/` are copied here as a separate step.
- These binaries are generic per platform. The reservation-specific behavior comes from the generated `modelDescription.xml` and `resources/config.json`.
- The runtime binaries connect to the Gateway public WSS facade; the real provider FMU remains on Lab Station.
