# FMU Data Directory

This directory stores `.fmu` files used by the `fmu-runner` service.

## Included files

The `.fmu` files at the root of this directory and the `test-fmus/` folder are
**example and test models only**. They are included in the repository so that
a freshly cloned or deployed Lab Gateway can be tested end-to-end without
needing external files.

Do not use them in a production lab listing — they are not associated with any
on-chain resource and exist purely for development and integration testing.

## Structure

```
fmu-data/
├── BouncingBall.fmu          # Example model (included for testing)
├── Dahlquist.fmu             # Example model (included for testing)
├── ...                       # Other bundled example models
├── test-fmus/                # Source and build scripts for test models
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
