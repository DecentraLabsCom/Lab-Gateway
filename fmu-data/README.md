# FMU Data Directory

This directory stores `.fmu` files provisioned by providers for simulation.

## Structure

```
fmu-data/
├── provider-0xABC123/        # Sub-directory per provider wallet
│   ├── spring-damper.fmu
│   └── dc-motor.fmu
└── provider-0xDEF456/
    └── heat-exchanger.fmu
```

## Notes

- The `fmu-runner` service mounts this directory as **read-only**.
- FMU files are identified by the `accessKey` field stored on-chain (same as `fmuFileName` in the NFT metadata).
- Marketplace upload is intentionally disabled.
- Providers must place FMU files here directly on Lab Station/Lab Gateway.
