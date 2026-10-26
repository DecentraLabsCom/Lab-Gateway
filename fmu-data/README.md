# Gateway FMU Development Data

This directory is mounted read-only by the Gateway FMU facade and its local
FMU Executor profile for development and validation. Its files are ignored by
Git and are not included in Gateway images or release packages. It is not the
production location for provider FMUs: production `station` mode keeps the
model on the selected Lab Station.

## Local fixtures

The canonical Smart Warehouse and reference FMU examples are maintained in
[FMU-Executor](https://github.com/DecentraLabsCom/FMU-Executor/tree/main/examples).
To refresh the local Gateway copies from a workspace containing both
repositories, run:

```powershell
python "Lab Gateway/scripts/sync_fmu_examples.py" `
  --examples-root "FMU-Executor/examples"
```

The default sync copies the six reference FMUs and Smart Warehouse Cell. It
selects the Linux x64 Smart Warehouse FMU for the local Executor. During AAS
synchronization, a selected GLB or Three.js app is copied to the Gateway's
immutable asset volume; this directory is not exposed through a public file
route. In production, the selected same-stem companion is read from the Lab
Station.

For the FMU storage layout, access-key mapping and example artifact details,
see the Executor's [provisioning guide](https://github.com/DecentraLabsCom/FMU-Executor/blob/main/README.md#fmu-provisioning).
