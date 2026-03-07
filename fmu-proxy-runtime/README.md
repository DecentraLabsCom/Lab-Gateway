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
- If the platform binaries are missing, `GET /api/v1/fmu/proxy/{labId}` will return `503 FMU proxy runtime binaries are not provisioned on Lab Station`.
