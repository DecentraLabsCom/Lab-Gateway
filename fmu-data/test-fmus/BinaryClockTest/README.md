# BinaryClockTest Gateway fixture

The canonical source and Windows/Linux builds now live in
`FMU-Executor/examples/reference-fmus/BinaryClockTest`. Build the platform
binary there, then refresh the Gateway development copies from the workspace
root with:

```powershell
python "Lab Gateway/scripts/sync_fmu_examples.py" --examples-root "FMU-Executor/examples"
```

`validate.py` validates the `BinaryClockTest.fmu` copy at the root of Gateway's
`fmu-data` directory. The Gateway keeps that runtime copy for development and
integration checks; it no longer maintains a second source/build definition.
