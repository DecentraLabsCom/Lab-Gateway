# FMU Data Directory

This directory stores `.fmu` files used by the `fmu-runner` service.

## Local development files

The files at the root of this directory are ignored local development/test
copies from `FMU-Executor/examples`. The six reference FMUs and Smart Warehouse
are included by the normal local sync. Lab Gateway does not vendor these demo
artifacts.

Reference FMUs and their Linux x86_64 builds are canonical in
`FMU-Executor/examples/reference-fmus`; the six tracked archives are copied by
the normal local sync. FMI 2 models use the `linux64` archive directory; FMI 3
models use `x86_64-linux`. Smart Warehouse Cell is canonical in
`FMU-Executor/examples/smart-warehouse-cell`; Gateway locally syncs its
Linux x64 FMU, companion GLB, Three.js application ZIP and license by default.
These local copies remain available for previews and tests but are not
committed. To refresh the reference examples and Smart Warehouse in Gateway's
local development folder:

```powershell
python "Lab Gateway/scripts/sync_fmu_examples.py" `
  --examples-root "FMU-Executor/examples"
```

The default sync validates and copies the reference FMUs and Smart Warehouse.
It installs `SmartWarehouseCell-linux64.fmu` as `SmartWarehouseCell.fmu`; do
not use its Windows Station build in the local executor. During AAS
synchronization, Gateway imports the selected GLB scene
or Three.js app into its public immutable asset volume; this directory itself
is not exposed through a public file route. Production mode retrieves the
selected same-stem asset from Lab Station instead.

These Gateway copies are development data only. They are ignored by Git and
are not included in Gateway images or release packages. The six reference FMUs
remain part of the FMU-Executor examples and are included in Lab Station
Windows and Linux x86_64 releases; the Linux arm64 release includes the three
examples that have arm64 binaries. Providers can also provision compatible
FMUs on a Station when creating their own labs.

## Structure

```
fmu-data/
├── SmartWarehouseCell.fmu     # Smart Warehouse demo (Linux x64 for local mode)
├── SmartWarehouseCell.glb     # Same-stem companion scene
├── SmartWarehouseCell.webapp.zip # Static Three.js app
├── SmartWarehouseCell.LICENSE.txt
├── BinaryClockTest.fmu        # FMI 3 reference fixture (default sync)
├── BouncingBall.fmu           # FMI 2 reference model (default sync)
├── Feedthrough.fmu            # FMI 2 reference model (default sync)
├── Stair.fmu                  # FMI 3 reference model (default sync)
├── StateSpace.fmu             # FMI 3 reference model (default sync)
├── VanDerPol.fmu              # FMI 3 reference model (default sync)
├── Reference-FMUs.LICENSE.txt # reference examples license
├── test-fmus/                 # Local validation helper for BinaryClockTest
└── provider-0xABC123/        # Runtime: per-provider sub-directory (git-ignored)
    └── spring-damper.fmu     #   Placed by the provider at deployment time
```

## Adding production FMU files

Providers upload their `.fmu` files to the Lab Gateway (or Lab Station) as part
of the lab setup process. The recommended path is a sub-directory named after
the provider wallet address:

```
fmu-data/provider-<wallet-address>/your-model.fmu
```

Files placed in `provider-0x.../` sub-directories are git-ignored so that
production data never ends up committed to the repository.

## Notes

- The `fmu-runner` service mounts this directory as **read-only**.
- The `fmuFileName` stored on-chain (and in the NFT metadata) must exactly
  match the filename on disk, including capitalisation.
- Provider sub-directories (`provider-0x.../`) are git-ignored to prevent
  production FMU files from being committed to the repository.
