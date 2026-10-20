# FMU Data Directory

This directory stores `.fmu` files used by the `fmu-runner` service.

## Local development files

The `.fmu` files at the root of this directory are development and test copies
of the canonical examples in `FMU-Executor/examples`. The reference models and
Smart Warehouse FMU/scene/app assets are generated locally by the sync script
and ignored by Git. FMU-Executor is their only canonical repository; Lab
Gateway does not vendor copies. To prepare all examples in a fresh workspace,
run the sync command below.

Reference FMUs and their Linux x86_64 builds are canonical in
`FMU-Executor/examples/reference-fmus`. FMI 2 models use the `linux64` archive
directory; FMI 3 models use `x86_64-linux`. Smart Warehouse Cell is canonical
in `FMU-Executor/examples/smart-warehouse-cell`; Gateway locally syncs its
Linux x64 FMU, companion GLB, Three.js application ZIP and license. These
local copies remain available to the demo and tests but are not committed. To
refresh all Gateway copies from the workspace root:

```powershell
python "Lab Gateway/scripts/sync_fmu_examples.py" `
  --examples-root "FMU-Executor/examples"
```

The sync script checks that every FMU contains a Linux x86_64 binary before
copying it. It installs `SmartWarehouseCell-linux64.fmu` as
`SmartWarehouseCell.fmu`; do not use its Windows Station build in the local
executor. During AAS synchronization, Gateway imports the selected GLB scene
or Three.js app into its public immutable asset volume; this directory itself
is not exposed through a public file route. Production mode retrieves the
selected same-stem asset from Lab Station instead.

Do not use them in a production lab listing — they are not associated with any
on-chain resource and exist purely for development and integration testing.

## Structure

```
fmu-data/
├── SmartWarehouseCell.fmu     # Smart Warehouse demo (Linux x64 for local mode)
├── SmartWarehouseCell.glb     # Same-stem companion scene
├── SmartWarehouseCell.webapp.zip # Static Three.js app
├── SmartWarehouseCell.LICENSE.txt
├── BinaryClockTest.fmu        # FMI 3 Binary and Clock fixture
├── BouncingBall.fmu           # FMI 2 reference model
├── Feedthrough.fmu            # FMI 2 reference model
├── Stair.fmu                  # FMI 3 reference model
├── StateSpace.fmu             # FMI 3 reference model
├── VanDerPol.fmu              # FMI 3 reference model
├── Reference-FMUs.LICENSE.txt # License for the upstream reference models
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
