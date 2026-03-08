import argparse
import json
import shutil
from pathlib import Path

from fmpy import extract, instantiate_fmu, read_model_description


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load and simulate a downloaded proxy.fmu with FMPy on the Windows host."
    )
    parser.add_argument("fmu", help="Path to the proxy.fmu artifact")
    parser.add_argument("--stop-time", type=float, default=None)
    parser.add_argument("--step-size", type=float, default=None)
    parser.add_argument("--extract-dir", default=None)
    return parser.parse_args()


def _selected_outputs(model_description):
    variables = []
    for variable in model_description.modelVariables:
        causality = (variable.causality or "").lower()
        if causality == "output":
            variables.append(variable)
    return variables


def _coerce_dimension_extent(value):
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise RuntimeError(f"Invalid dimension extent value: {value}")
        value = value[0]
    return int(value)


def _variable_by_value_reference(model_description):
    return {int(variable.valueReference): variable for variable in model_description.modelVariables}


def _resolve_dimension_extent(fmu, variable_by_vr, dimension):
    if getattr(dimension, "start", None) is not None:
        return _coerce_dimension_extent(dimension.start)
    if getattr(dimension, "valueReference", None) is not None:
        referenced = variable_by_vr.get(int(dimension.valueReference))
        if referenced is None:
            raise RuntimeError(f"Unknown dimension valueReference: {dimension.valueReference}")
        variable_type = str(referenced.type)
        getter_name = f"get{variable_type}"
        getter = getattr(fmu, getter_name, None)
        if getter is None:
            raise RuntimeError(f"Unsupported structural parameter type for dimension resolution: {variable_type}")
        values = getter([int(referenced.valueReference)])
        return _coerce_dimension_extent(values[0])
    if getattr(dimension, "variable", None) is not None and getattr(dimension.variable, "start", None) is not None:
        return _coerce_dimension_extent(dimension.variable.start)
    raise RuntimeError("Unable to resolve dimension extent")


def _variable_flat_size(fmu, variable_by_vr, variable):
    dimensions = getattr(variable, "dimensions", None) or []
    if not dimensions:
        return 1
    size = 1
    for dimension in dimensions:
        size *= _resolve_dimension_extent(fmu, variable_by_vr, dimension)
    return size


def _read_outputs(fmu, model_description, variables):
    variable_by_vr = _variable_by_value_reference(model_description)
    by_type = {}
    for variable in variables:
        variable_type = str(variable.type)
        if variable_type == 'Enumeration':
            variable_type = 'Integer'
        by_type.setdefault(variable_type, []).append(variable)

    values = {}
    for variable_type, typed_variables in by_type.items():
        getter_name = f'get{variable_type}'
        getter = getattr(fmu, getter_name, None)
        if getter is None:
            raise RuntimeError(f'Unsupported FMU output type for validation helper: {variable_type}')
        refs = [int(variable.valueReference) for variable in typed_variables]
        total_values = sum(_variable_flat_size(fmu, variable_by_vr, variable) for variable in typed_variables)
        raw_values = getter(refs, nValues=total_values) if total_values != len(refs) else getter(refs)
        offset = 0
        for variable in typed_variables:
            value_count = _variable_flat_size(fmu, variable_by_vr, variable)
            segment = raw_values[offset: offset + value_count]
            offset += value_count
            if variable_type in ('Real', 'Float32', 'Float64'):
                normalized = [float(value) for value in segment]
            elif variable_type in ('Integer', 'Int8', 'UInt8', 'Int16', 'UInt16', 'Int32', 'UInt32', 'Int64', 'UInt64'):
                normalized = [int(value) for value in segment]
            elif variable_type == 'Boolean':
                normalized = [bool(value) for value in segment]
            elif variable_type == 'String':
                normalized = [value.decode('utf-8') if isinstance(value, bytes) else str(value) for value in segment]
            else:
                raise RuntimeError(f'Unsupported FMU output type for validation helper: {variable_type}')
            values[variable.name] = normalized[0] if value_count == 1 else normalized
    return values


def main() -> int:
    args = parse_args()
    fmu_path = Path(args.fmu)
    if not fmu_path.is_file():
        raise SystemExit(f"FMU not found: {fmu_path}")

    model_description = read_model_description(str(fmu_path))
    default_experiment = getattr(model_description, "defaultExperiment", None)
    start_time = float(getattr(default_experiment, "startTime", 0.0) or 0.0)
    default_stop = float(getattr(default_experiment, "stopTime", 0.1) or 0.1)
    default_step = float(getattr(default_experiment, "stepSize", 0.01) or 0.01)
    stop_time = args.stop_time if args.stop_time is not None else min(default_stop, start_time + 0.1)
    if stop_time <= start_time:
        stop_time = start_time + max(default_step, 0.01)
    step_size = args.step_size if args.step_size is not None else default_step
    extract_dir = Path(args.extract_dir) if args.extract_dir else fmu_path.with_suffix("")
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.parent.mkdir(parents=True, exist_ok=True)
    extract(str(fmu_path), unzipdir=str(extract_dir))

    output_variables = _selected_outputs(model_description)
    current_time = start_time
    outputs = {}
    fmi_major = int(str(getattr(model_description, 'fmiVersion', '2.0')).split('.', 1)[0] or '2')
    fmu = instantiate_fmu(str(extract_dir), model_description, fmi_type="CoSimulation")
    try:
        fmu.instantiate()
        if fmi_major < 3:
            fmu.setupExperiment(startTime=start_time, stopTime=stop_time)
            fmu.enterInitializationMode()
        else:
            fmu.enterInitializationMode(startTime=start_time, stopTime=stop_time)
        fmu.exitInitializationMode()
        while current_time < stop_time:
            delta = min(step_size, stop_time - current_time)
            fmu.doStep(currentCommunicationPoint=current_time, communicationStepSize=delta)
            current_time += delta
        outputs = _read_outputs(fmu, model_description, output_variables)
        fmu.terminate()
    finally:
        try:
            fmu.freeInstance()
        except Exception:
            pass

    summary = {
        "modelName": getattr(model_description, "modelName", None),
        "fmiVersion": getattr(model_description, "fmiVersion", None),
        "startTime": start_time,
        "stopTime": stop_time,
        "stepSize": step_size,
        "finalTime": current_time,
        "finalOutputs": outputs,
        "extractDir": str(extract_dir),
    }
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
