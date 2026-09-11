import base64
from typing import Optional


def _normalize_xml_value(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _parse_fmi_major_version(value) -> int:
    text = str(value or "").strip()
    if not text:
        return 2
    try:
        return int(text.split(".", 1)[0])
    except ValueError:
        return 2


def _normalize_proxy_fmi3_type(type_name: Optional[str]) -> str:
    normalized = str(type_name or "").strip()
    if normalized in {"Float32", "Float64", "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64", "Boolean", "String", "Binary", "Clock"}:
        return normalized
    if normalized == "Enumeration":
        return "Int32"
    if normalized == "Integer":
        return "Int32"
    if normalized:
        return normalized
    return "Float64"


def _format_fmi_start_value(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return " ".join(_format_fmi_start_value(item) or "" for item in value)
    return str(value)


def _format_fmi3_binary_start_value(raw_value, formatted_value: str) -> str:
    """Serialize a Binary start value using FMI 3's hexBinary representation."""
    if isinstance(raw_value, (bytes, bytearray)):
        return bytes(raw_value).hex()
    if isinstance(raw_value, str):
        try:
            return base64.b64decode(raw_value, validate=True).hex()
        except ValueError:
            return formatted_value
    return formatted_value


def _collect_declared_type_definitions(model_metadata: dict) -> dict[str, dict]:
    definitions: dict[str, dict] = {}
    for variable in model_metadata.get("modelVariables", []):
        declared_type = variable.get("declaredType")
        if not isinstance(declared_type, dict):
            continue
        type_name = _normalize_xml_value(declared_type.get("name"))
        if not type_name:
            continue
        definitions.setdefault(type_name, declared_type)
    return definitions


def _normalize_metadata_value(value, variable_type: Optional[str] = None):
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if variable_type in {"Int64", "UInt64"}:
        if isinstance(value, (list, tuple)):
            return [str(int(item)) for item in value]
        return str(int(value))
    if isinstance(value, (list, tuple)):
        return [_normalize_metadata_value(item, variable_type=variable_type) for item in value]
    return value


def _collect_variable_dimensions(var) -> list[dict]:
    dimensions = []
    for dimension in getattr(var, "dimensions", []) or []:
        entry = {}
        if getattr(dimension, "start", None) is not None:
            entry["start"] = int(dimension.start)
        if getattr(dimension, "valueReference", None) is not None:
            entry["valueReference"] = int(dimension.valueReference)
        variable = getattr(dimension, "variable", None)
        if variable is not None and getattr(variable, "name", None):
            entry["variableName"] = variable.name
        if entry:
            dimensions.append(entry)
    return dimensions


def _model_metadata_from_model_description(md) -> dict:
    supports_cs = bool(getattr(md, "coSimulation", None))
    supports_me = bool(getattr(md, "modelExchange", None))
    simulation_kind = "coSimulation" if supports_cs else ("modelExchange" if supports_me else "unknown")
    simulation_type = "CoSimulation" if supports_cs else ("ModelExchange" if supports_me else "Unknown")

    default_experiment = getattr(md, "defaultExperiment", None)
    default_start = float(default_experiment.startTime) if default_experiment and default_experiment.startTime is not None else 0.0
    default_stop = float(default_experiment.stopTime) if default_experiment and default_experiment.stopTime is not None else 1.0
    default_step = float(default_experiment.stepSize) if default_experiment and default_experiment.stepSize is not None else 0.01
    default_tolerance: Optional[float] = None
    if default_experiment is not None:
        raw_tolerance = getattr(default_experiment, "tolerance", None)
        if raw_tolerance is not None:
            default_tolerance = float(raw_tolerance)

    variables = []
    for index, var in enumerate(getattr(md, "modelVariables", []), start=1):
        entry = {
            "name": var.name,
            "causality": var.causality or "local",
            "type": str(var.type),
            "variability": getattr(var, "variability", None) or "continuous",
            "valueReference": int(getattr(var, "valueReference", index)),
        }
        if hasattr(var, "initial") and var.initial:
            entry["initial"] = var.initial
        if hasattr(var, "unit") and var.unit:
            entry["unit"] = var.unit
        if hasattr(var, "start") and var.start is not None:
            entry["start"] = _normalize_metadata_value(var.start, variable_type=str(var.type))
        if hasattr(var, "min") and var.min is not None:
            entry["min"] = var.min
        if hasattr(var, "max") and var.max is not None:
            entry["max"] = var.max
        if hasattr(var, "description") and var.description:
            entry["description"] = var.description
        if hasattr(var, "quantity") and var.quantity:
            entry["quantity"] = var.quantity
        if hasattr(var, "displayUnit") and var.displayUnit:
            entry["displayUnit"] = var.displayUnit
        if hasattr(var, "nominal") and var.nominal is not None:
            entry["nominal"] = var.nominal
        declared_type = getattr(var, "declaredType", None)
        if declared_type is not None and getattr(declared_type, "name", None):
            declared_type_entry = {
                "name": declared_type.name,
                "type": str(getattr(declared_type, "type", None) or var.type),
            }
            if getattr(declared_type, "description", None):
                declared_type_entry["description"] = declared_type.description
            items = []
            for item in getattr(declared_type, "items", []) or []:
                item_entry = {
                    "name": str(getattr(item, "name", "") or ""),
                    "value": str(getattr(item, "value", "") or ""),
                }
                if getattr(item, "description", None):
                    item_entry["description"] = item.description
                items.append(item_entry)
            if items:
                declared_type_entry["items"] = items
            entry["declaredType"] = declared_type_entry
        dimensions = _collect_variable_dimensions(var)
        if dimensions:
            entry["dimensions"] = dimensions
        variables.append(entry)

    interface = getattr(md, "coSimulation", None) or getattr(md, "modelExchange", None)
    capabilities: dict = {}
    if interface:
        for attribute in (
            "canGetAndSetFMUstate",
            "canSerializeFMUstate",
            "canHandleVariableCommunicationStepSize",
            "providesDirectionalDerivative",
            "providesAdjointDerivatives",
        ):
            value = getattr(interface, attribute, None)
            if value is not None:
                capabilities[attribute] = bool(value)
        fixed = getattr(interface, "fixedInternalStepSize", None)
        if fixed is not None:
            capabilities["fixedInternalStepSize"] = float(fixed)

    unit_definitions: list = []
    for unit in getattr(md, "unitDefinitions", []) or []:
        unit_entry: dict = {"name": unit.name}
        base_unit = getattr(unit, "baseUnit", None)
        if base_unit is not None:
            base: dict = {}
            for exponent in ("kg", "m", "s", "A", "K", "mol", "cd", "rad"):
                value = int(getattr(base_unit, exponent, 0) or 0)
                if value != 0:
                    base[exponent] = value
            factor = getattr(base_unit, "factor", None)
            if factor is not None and float(factor) != 1.0:
                base["factor"] = float(factor)
            offset = getattr(base_unit, "offset", None)
            if offset is not None and float(offset) != 0.0:
                base["offset"] = float(offset)
            if base:
                unit_entry["baseUnit"] = base
        display_units: list = []
        for display_unit in getattr(unit, "displayUnits", []) or []:
            display_entry: dict = {"name": display_unit.name}
            factor = getattr(display_unit, "factor", None)
            if factor is not None and float(factor) != 1.0:
                display_entry["factor"] = float(factor)
            offset = getattr(display_unit, "offset", None)
            if offset is not None and float(offset) != 0.0:
                display_entry["offset"] = float(offset)
            display_units.append(display_entry)
        if display_units:
            unit_entry["displayUnits"] = display_units
        unit_definitions.append(unit_entry)

    return {
        "modelName": _normalize_xml_value(getattr(md, "modelName", None)) or "DecentraLabsProxy",
        "guid": _normalize_xml_value(getattr(md, "guid", None)),
        "instantiationToken": _normalize_xml_value(getattr(md, "instantiationToken", None)),
        "fmiVersion": md.fmiVersion,
        "simulationKind": simulation_kind,
        "simulationType": simulation_type,
        "supportsCoSimulation": supports_cs,
        "supportsModelExchange": supports_me,
        "defaultStartTime": default_start,
        "defaultStopTime": default_stop,
        "defaultStepSize": default_step,
        "defaultTolerance": default_tolerance,
        "modelVariables": variables,
        "description": _normalize_xml_value(getattr(md, "description", None)) or "",
        "author": _normalize_xml_value(getattr(md, "author", None)) or "",
        "version": _normalize_xml_value(getattr(md, "version", None)) or "",
        "license": _normalize_xml_value(getattr(md, "license", None)) or "",
        "generationTool": _normalize_xml_value(getattr(md, "generationTool", None)) or "",
        "capabilities": capabilities,
        "unitDefinitions": unit_definitions,
    }


def _public_model_metadata(metadata: dict) -> dict:
    variables = []
    for variable in metadata.get("modelVariables", []):
        entry = {
            "name": variable.get("name"),
            "causality": variable.get("causality", "local"),
            "type": variable.get("type", "Real"),
            "variability": variable.get("variability", "continuous"),
        }
        for optional_key in ("initial", "unit", "start", "min", "max", "dimensions"):
            if optional_key in variable:
                entry[optional_key] = variable[optional_key]
        variables.append(entry)

    payload = {
        "fmiVersion": metadata.get("fmiVersion", "2.0"),
        "simulationKind": metadata.get("simulationKind", "unknown"),
        "simulationType": metadata.get("simulationType", "Unknown"),
        "supportsCoSimulation": bool(metadata.get("supportsCoSimulation")),
        "supportsModelExchange": bool(metadata.get("supportsModelExchange")),
        "defaultStartTime": float(metadata.get("defaultStartTime", 0.0)),
        "defaultStopTime": float(metadata.get("defaultStopTime", 1.0)),
        "defaultStepSize": float(metadata.get("defaultStepSize", 0.01)),
        "modelVariables": variables,
    }
    if metadata.get("instantiationToken"):
        payload["instantiationToken"] = metadata["instantiationToken"]
    return payload