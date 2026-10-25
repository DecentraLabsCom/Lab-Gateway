import base64
import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Optional


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


def _finite_fmi_number(value, *, integer: bool = False):
    if value is None:
        return None
    try:
        parsed = int(value) if integer else float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(parsed, float) and not math.isfinite(parsed):
        return None
    return parsed


def _display_unit_metadata(md, var, declared_type, display_unit_inverses=None) -> Optional[dict]:
    unit_name = getattr(var, "unit", None) or getattr(declared_type, "unit", None)
    display_name = getattr(var, "displayUnit", None) or getattr(declared_type, "displayUnit", None)
    if not isinstance(unit_name, str) or not unit_name or not isinstance(display_name, str) or not display_name:
        return None

    unit = next(
        (item for item in (getattr(md, "unitDefinitions", None) or []) if getattr(item, "name", None) == unit_name),
        None,
    )
    display = next(
        (item for item in (getattr(unit, "displayUnits", None) or []) if getattr(item, "name", None) == display_name),
        None,
    )
    if display is None:
        return None

    try:
        factor = float(getattr(display, "factor", 1.0))
        offset = float(getattr(display, "offset", 0.0))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(factor) or factor == 0 or not math.isfinite(offset):
        return None

    fmi_major_version = _parse_fmi_major_version(getattr(md, "fmiVersion", None))
    raw_inverse = getattr(display, "inverse", None)
    if raw_inverse is None:
        inverse_map = display_unit_inverses
        if _parse_fmi_major_version(getattr(md, "fmiVersion", None)) == 3 and inverse_map is None:
            return None
        inverse = bool(inverse_map and inverse_map.get((unit_name, display_name), False))
    else:
        inverse = raw_inverse is True or str(raw_inverse).strip().lower() in {"true", "1"}
    if inverse and (fmi_major_version == 1 or offset != 0):
        return None

    # Normalize FMI 1 and FMI 2/3 to display = factor * model_value + offset.
    if fmi_major_version == 1:
        factor, offset = 1.0 / factor, -offset / factor
    variable_relative = getattr(var, "relativeQuantity", None)
    type_relative = getattr(declared_type, "relativeQuantity", None)
    if (
        variable_relative is True
        or type_relative is True
        or str(variable_relative).strip().lower() in {"true", "1"}
        or str(type_relative).strip().lower() in {"true", "1"}
    ):
        offset = 0.0
    result: dict[str, Any] = {"name": display_name, "factor": factor, "offset": offset}
    if inverse:
        result["inverse"] = True
    return result


def _display_unit_inverse_map_from_fmu(fmu_path) -> dict[tuple[str, str], bool] | None:
    """Read FMI 3 inverse display units omitted by some FMPy releases."""
    try:
        with zipfile.ZipFile(fmu_path) as archive:
            info = archive.getinfo("modelDescription.xml")
            if info.file_size > 16 * 1024 * 1024:
                return None
            with archive.open(info) as source:
                root = ET.parse(source).getroot()
    except (OSError, KeyError, RuntimeError, ET.ParseError, zipfile.BadZipFile):
        return None

    def children_named(element, name):
        return (child for child in element if child.tag.rsplit("}", 1)[-1] == name)

    unit_definitions = next(children_named(root, "UnitDefinitions"), None)
    inverse_units: dict[tuple[str, str], bool] = {}
    if unit_definitions is None:
        return inverse_units
    for unit in children_named(unit_definitions, "Unit"):
        unit_name = unit.get("name")
        if not unit_name:
            continue
        for display in children_named(unit, "DisplayUnit"):
            display_name = display.get("name")
            inverse = str(display.get("inverse", "false")).strip().lower() in {"true", "1"}
            if display_name and inverse:
                inverse_units[(unit_name, display_name)] = True
    return inverse_units


def _model_metadata_from_model_description(
    md,
    *,
    include_internal_variables: bool = True,
    display_unit_inverses: dict[tuple[str, str], bool] | None = None,
) -> dict:
    supports_cs = bool(getattr(md, "coSimulation", None))
    supports_me = bool(getattr(md, "modelExchange", None))
    simulation_kind = "coSimulation" if supports_cs else ("modelExchange" if supports_me else "unknown")
    simulation_type = "CoSimulation" if supports_cs else ("ModelExchange" if supports_me else "Unknown")

    default_experiment = getattr(md, "defaultExperiment", None)
    default_start = (
        float(default_experiment.startTime)
        if default_experiment and default_experiment.startTime is not None
        else None
    )
    default_stop = (
        float(default_experiment.stopTime)
        if default_experiment and default_experiment.stopTime is not None
        else None
    )
    default_step = (
        float(default_experiment.stepSize)
        if default_experiment and default_experiment.stepSize is not None
        else None
    )
    default_tolerance: Optional[float] = None
    if default_experiment is not None:
        raw_tolerance = getattr(default_experiment, "tolerance", None)
        if raw_tolerance is not None:
            default_tolerance = float(raw_tolerance)

    variables = []
    integer_types = {
        "Integer", "Enumeration", "Int8", "UInt8", "Int16", "UInt16",
        "Int32", "UInt32", "Int64", "UInt64",
    }
    for index, var in enumerate(getattr(md, "modelVariables", []), start=1):
        # Local variables describe internal implementation state. They remain
        # available to internal callers when needed, but are not FMI ports and
        # should not inflate Gateway describe responses for large models.
        if not include_internal_variables and getattr(var, "causality", None) == "local":
            continue
        entry = {
            "name": var.name,
            "causality": var.causality or "local",
            "type": str(var.type),
            "variability": getattr(var, "variability", None) or "continuous",
            "valueReference": int(getattr(var, "valueReference", index)),
        }
        declared_type = getattr(var, "declaredType", None)
        if hasattr(var, "initial") and var.initial:
            entry["initial"] = var.initial
        unit = getattr(var, "unit", None) or getattr(declared_type, "unit", None)
        if unit:
            entry["unit"] = unit
        if hasattr(var, "start") and var.start is not None:
            entry["start"] = _normalize_metadata_value(var.start, variable_type=str(var.type))
        minimum = getattr(var, "min", None)
        if minimum is None:
            minimum = getattr(declared_type, "min", None)
        maximum = getattr(var, "max", None)
        if maximum is None:
            maximum = getattr(declared_type, "max", None)
        normalized_min = _finite_fmi_number(minimum, integer=str(var.type) in integer_types)
        normalized_max = _finite_fmi_number(maximum, integer=str(var.type) in integer_types)
        if normalized_min is not None:
            entry["min"] = normalized_min
        if normalized_max is not None:
            entry["max"] = normalized_max
        if hasattr(var, "description") and var.description:
            entry["description"] = str(var.description).strip()[:4096]
        quantity = getattr(var, "quantity", None) or getattr(declared_type, "quantity", None)
        if quantity:
            entry["quantity"] = quantity
        display_name = getattr(var, "displayName", None)
        if isinstance(display_name, str) and display_name.strip():
            entry["displayName"] = display_name.strip()[:256]
        display_unit = _display_unit_metadata(md, var, declared_type, display_unit_inverses)
        if display_unit is not None:
            entry["displayUnit"] = display_unit
        if hasattr(var, "nominal") and var.nominal is not None:
            entry["nominal"] = var.nominal
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
                enum_items = []
                for item in items:
                    value = _finite_fmi_number(item.get("value"), integer=True)
                    name = item.get("name")
                    if value is None or not name:
                        continue
                    enum_item = {"value": value, "name": str(name)[:256]}
                    if item.get("description"):
                        enum_item["description"] = str(item["description"])[:1024]
                    enum_items.append(enum_item)
                if str(var.type) == "Enumeration" and enum_items and len(enum_items) <= 256:
                    entry["enumItems"] = enum_items
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
        if variable.get("causality", "local") == "local":
            continue
        entry = {
            "name": variable.get("name"),
            "causality": variable.get("causality", "local"),
            "type": variable.get("type", "Real"),
            "variability": variable.get("variability", "continuous"),
        }
        for optional_key in (
            "valueReference", "initial", "unit", "start", "min", "max", "dimensions",
            "description", "displayName", "displayUnit", "enumItems", "nominal",
            "quantity", "declaredType",
        ):
            if optional_key in variable:
                entry[optional_key] = variable[optional_key]
        variables.append(entry)

    payload = {
        "fmiVersion": metadata.get("fmiVersion", "2.0"),
        "simulationKind": metadata.get("simulationKind", "unknown"),
        "simulationType": metadata.get("simulationType", "Unknown"),
        "supportsCoSimulation": bool(metadata.get("supportsCoSimulation")),
        "supportsModelExchange": bool(metadata.get("supportsModelExchange")),
        "modelVariables": variables,
    }
    for key in ("defaultStartTime", "defaultStopTime", "defaultStepSize"):
        if metadata.get(key) is not None:
            payload[key] = float(metadata[key])
    if metadata.get("instantiationToken"):
        payload["instantiationToken"] = metadata["instantiationToken"]
    return payload
