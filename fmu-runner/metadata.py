import base64
import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Optional
from fmi_ls_struct import normalize_fmi_ls_struct


def _normalize_xml_value(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_fmi_boolean(value) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    return None


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
        return "Enumeration"
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
    raw_definitions = model_metadata.get("typeDefinitions")
    if isinstance(raw_definitions, list):
        for declared_type in raw_definitions:
            if not isinstance(declared_type, dict):
                continue
            type_name = _normalize_xml_value(declared_type.get("name"))
            if type_name:
                definitions.setdefault(type_name, declared_type)
    for variable in model_metadata.get("modelVariables", []):
        declared_type = variable.get("declaredType")
        if not isinstance(declared_type, dict):
            continue
        type_name = _normalize_xml_value(declared_type.get("name"))
        if not type_name:
            continue
        definitions.setdefault(type_name, declared_type)
    return definitions


def _normalize_metadata_value(value: Any, variable_type: Optional[str] = None) -> Any:
    if hasattr(value, "tolist") and callable(value.tolist):
        value = value.tolist()
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if variable_type in {"Int64", "UInt64", "Enumeration"}:
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
    root = _read_model_description_xml(fmu_path)
    if root is None:
        return None
    unit_definitions = next(_xml_children_named(root, "UnitDefinitions"), None)
    inverse_units: dict[tuple[str, str], bool] = {}
    if unit_definitions is None:
        return inverse_units
    for unit in _xml_children_named(unit_definitions, "Unit"):
        unit_name = unit.get("name")
        if not unit_name:
            continue
        for display in _xml_children_named(unit, "DisplayUnit"):
            display_name = display.get("name")
            inverse = str(display.get("inverse", "false")).strip().lower() in {"true", "1"}
            if display_name and inverse:
                inverse_units[(unit_name, display_name)] = True
    return inverse_units


_MAX_MODEL_DESCRIPTION_XML_BYTES = 16 * 1024 * 1024


def _read_model_description_xml(fmu_path) -> ET.Element | None:
    """Read a size-bounded source modelDescription.xml for metadata fallback."""
    try:
        with zipfile.ZipFile(fmu_path) as archive:
            info = archive.getinfo("modelDescription.xml")
            if info.file_size > _MAX_MODEL_DESCRIPTION_XML_BYTES:
                return None
            with archive.open(info) as source:
                xml_bytes = source.read(_MAX_MODEL_DESCRIPTION_XML_BYTES + 1)
                if len(xml_bytes) > _MAX_MODEL_DESCRIPTION_XML_BYTES:
                    return None
                root = ET.fromstring(xml_bytes)
    except (OSError, KeyError, RuntimeError, ET.ParseError, zipfile.BadZipFile):
        return None
    return root


def _xml_children_named(element, name: str):
    return (child for child in element if child.tag.rsplit("}", 1)[-1] == name)


def _raw_fmi_type_definitions(
    root: ET.Element | None,
) -> tuple[list[dict], dict[str, dict[str, str]], dict[str, tuple[ET.Element, ET.Element]]]:
    """Parse named FMI type definitions directly when FMPy omits FMI 3 types."""
    if root is None:
        return [], {}, {}

    type_definitions_element = next(_xml_children_named(root, "TypeDefinitions"), None)
    definitions: list[dict] = []
    if type_definitions_element is not None:
        for source in type_definitions_element:
            tag = source.tag.rsplit("}", 1)[-1]
            if tag == "SimpleType":
                typed_source = next(iter(source), None)
                if typed_source is None:
                    continue
                type_name = typed_source.tag.rsplit("}", 1)[-1]
                description = source.get("description") or typed_source.get("description")
            else:
                typed_source = source
                type_name = tag[:-4] if tag.endswith("Type") else tag
                description = source.get("description")
            name = _normalize_xml_value(source.get("name"))
            if not name:
                continue
            definition: dict[str, Any] = {"name": name, "type": type_name}
            if description:
                definition["description"] = description[:4096]

            for field, maximum_length in (
                ("unit", 128), ("displayUnit", 256), ("quantity", 256),
                ("mimeType", 256), ("intervalVariability", 32),
            ):
                value = _normalize_xml_value(typed_source.get(field))
                if value:
                    definition[field] = value[:maximum_length]

            integer_type = type_name in {
                "Integer", "Enumeration", "Int8", "UInt8", "Int16", "UInt16",
                "Int32", "UInt32", "Int64", "UInt64",
            }
            for field in ("min", "max", "nominal", "intervalDecimal", "shiftDecimal"):
                value = typed_source.get(field)
                if value is None:
                    continue
                normalized = _finite_fmi_number(value, integer=integer_type and field in {"min", "max"})
                if normalized is not None:
                    definition[field] = normalized

            for field in ("relativeQuantity", "unbounded", "supportsFraction", "canBeDeactivated"):
                value = _normalize_fmi_boolean(typed_source.get(field))
                if value is not None:
                    definition[field] = value

            for field in ("maxSize", "priority", "resolution", "intervalCounter", "shiftCounter"):
                value = typed_source.get(field)
                if value is None:
                    continue
                normalized = _finite_fmi_number(value, integer=True)
                if normalized is not None and normalized >= 0:
                    definition[field] = normalized

            items = []
            for item in _xml_children_named(typed_source, "Item"):
                item_name = _normalize_xml_value(item.get("name"))
                item_value = item.get("value")
                if not item_name or item_value is None:
                    continue
                normalized_item = {"name": item_name[:256], "value": str(item_value)}
                item_description = _normalize_xml_value(item.get("description"))
                if item_description:
                    normalized_item["description"] = item_description[:1024]
                items.append(normalized_item)
            if items:
                definition["items"] = items
            definitions.append(definition)

    variable_types: dict[str, dict[str, str]] = {}
    variable_elements: dict[str, tuple[ET.Element, ET.Element]] = {}
    model_variables = next(_xml_children_named(root, "ModelVariables"), None)
    if model_variables is not None:
        for source in model_variables:
            tag = source.tag.rsplit("}", 1)[-1]
            if tag == "ScalarVariable":
                variable = next(iter(source), None)
                if variable is None:
                    continue
            else:
                variable = source
            variable_name = source.get("name")
            if variable_name:
                variable_elements[variable_name] = (source, variable)
            type_name = variable.get("declaredType")
            if variable_name and type_name:
                variable_types[variable_name] = {"name": type_name}
    return definitions, variable_types, variable_elements


def _display_unit_metadata_from_model_metadata(
    variable: dict,
    declared_type: dict | None,
    model_metadata: dict,
) -> dict | None:
    variable_display = variable.get("displayUnit")
    display_name = (
        variable_display.get("name")
        if isinstance(variable_display, dict)
        else variable_display
    ) or (declared_type or {}).get("displayUnit")
    unit_name = variable.get("unit") or (declared_type or {}).get("unit")
    if not isinstance(unit_name, str) or not isinstance(display_name, str):
        return None
    unit = next(
        (item for item in model_metadata.get("unitDefinitions", [])
         if isinstance(item, dict) and item.get("name") == unit_name),
        None,
    )
    display = next(
        (item for item in (unit or {}).get("displayUnits", [])
         if isinstance(item, dict) and item.get("name") == display_name),
        None,
    )
    if display is None:
        return None
    try:
        factor = float(display.get("factor", 1.0))
        offset = float(display.get("offset", 0.0))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(factor) or factor == 0 or not math.isfinite(offset):
        return None
    inverse = display.get("inverse") is True
    if inverse and offset != 0:
        return None
    if variable.get("relativeQuantity") is True:
        offset = 0.0
    return {"name": display_name, "factor": factor, "offset": offset, **({"inverse": True} if inverse else {})}


def _merge_raw_fmi_type_metadata(metadata: dict, fmu_path) -> dict:
    """Restore named types and effective FMI attributes hidden by parser omissions."""
    root = _read_model_description_xml(fmu_path)
    raw_definitions, variable_types, variable_elements = _raw_fmi_type_definitions(root)
    if not raw_definitions and not variable_types:
        return metadata

    existing_definitions = {
        definition.get("name"): definition
        for definition in metadata.get("typeDefinitions", [])
        if isinstance(definition, dict) and isinstance(definition.get("name"), str)
    }
    merged_definitions = []
    seen_names = set()
    for raw_definition in raw_definitions:
        name = raw_definition["name"]
        merged = {**existing_definitions.get(name, {}), **raw_definition}
        merged_definitions.append(merged)
        seen_names.add(name)
    merged_definitions.extend(
        definition for name, definition in existing_definitions.items() if name not in seen_names
    )
    if merged_definitions:
        metadata["typeDefinitions"] = merged_definitions

    type_definitions_by_name = {definition["name"]: definition for definition in merged_definitions}
    for variable in metadata.get("modelVariables", []):
        if not isinstance(variable, dict):
            continue
        variable_name = variable.get("name")
        source_variable = variable_elements.get(variable_name) if isinstance(variable_name, str) else None
        source_attributes: dict[str, str] = {}
        typed_source = None
        if source_variable is not None:
            source_element, typed_source = source_variable
            source_attributes.update(source_element.attrib)
            if typed_source is not source_element:
                source_attributes.update(typed_source.attrib)
            description = _normalize_xml_value(source_element.get("description"))
            if description:
                variable["description"] = description[:4096]
            for field, maximum_length in (
                ("causality", 32), ("variability", 32), ("initial", 32),
                ("unit", 128), ("quantity", 256), ("mimeType", 256),
                ("intervalVariability", 32),
            ):
                value = _normalize_xml_value(source_attributes.get(field))
                if value:
                    variable[field] = value[:maximum_length]
            raw_reinit = source_attributes.get("reinit")
            if raw_reinit in {"true", "false"}:
                variable["reinit"] = raw_reinit == "true"
            display_unit = _normalize_xml_value(source_attributes.get("displayUnit"))
            if display_unit and not variable.get("displayUnit"):
                variable["displayUnit"] = display_unit[:256]

            integer_type = str(variable.get("type", "")).lower() in {
                "integer", "enumeration", "int8", "uint8", "int16", "uint16",
                "int32", "uint32", "int64", "uint64",
            }
            for field in ("min", "max", "nominal", "intervalDecimal", "shiftDecimal"):
                value = source_attributes.get(field)
                if value is None:
                    continue
                normalized = _finite_fmi_number(value, integer=integer_type and field in {"min", "max"})
                if normalized is not None:
                    variable[field] = normalized
            for field in ("relativeQuantity", "unbounded", "canBeDeactivated", "supportsFraction"):
                value = _normalize_fmi_boolean(source_attributes.get(field))
                if value is not None:
                    variable[field] = value
            for field in ("maxSize", "priority", "resolution", "intervalCounter", "shiftCounter"):
                value = source_attributes.get(field)
                if value is None:
                    continue
                normalized = _finite_fmi_number(value, integer=True)
                if normalized is not None and normalized >= 0:
                    variable[field] = normalized

            aliases = []
            for raw_alias in _xml_children_named(typed_source, "Alias"):
                alias_name = _normalize_xml_value(raw_alias.get("name"))
                if not alias_name:
                    continue
                alias_entry = {"name": alias_name[:512]}
                for field, maximum_length in (("description", 4096), ("displayUnit", 256)):
                    value = _normalize_xml_value(raw_alias.get(field))
                    if value:
                        alias_entry[field] = value[:maximum_length]
                aliases.append(alias_entry)
            if aliases:
                variable["aliases"] = aliases

        reference = variable_types.get(variable_name) if isinstance(variable_name, str) else None
        definition = type_definitions_by_name.get(reference["name"]) if reference is not None else None
        if definition is not None:
            current = variable.get("declaredType")
            variable["declaredType"] = {
                **(current if isinstance(current, dict) else {}),
                **definition,
            }
            for field in (
                "unit", "quantity", "min", "max", "nominal", "mimeType", "maxSize",
                "intervalVariability", "intervalDecimal", "shiftDecimal", "supportsFraction",
                "resolution", "intervalCounter", "shiftCounter", "canBeDeactivated", "priority",
            ):
                if field not in variable and field in definition:
                    variable[field] = definition[field]
            if "displayUnit" not in variable and definition.get("displayUnit"):
                variable["displayUnit"] = definition["displayUnit"]
        if typed_source is not None:
            # FMPy represents some omitted variable-level boolean attributes as
            # default False. The source XML distinguishes those defaults from
            # explicit variable overrides, so inherit only when XML does not.
            for field in ("relativeQuantity", "unbounded"):
                explicit = _normalize_fmi_boolean(source_attributes.get(field))
                inherited = _normalize_fmi_boolean(definition.get(field)) if definition else None
                if explicit is not None:
                    variable[field] = explicit
                elif inherited is not None:
                    variable[field] = inherited
        normalized_display_unit = _display_unit_metadata_from_model_metadata(
            variable,
            definition,
            metadata,
        )
        if normalized_display_unit is not None:
            variable["displayUnit"] = normalized_display_unit
    return metadata


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
        interval_variability = getattr(var, "intervalVariability", None)
        declared_type = getattr(var, "declaredType", None)
        if interval_variability is None:
            interval_variability = getattr(declared_type, "intervalVariability", None)
        if isinstance(interval_variability, str) and interval_variability:
            entry["intervalVariability"] = interval_variability
        alias = getattr(var, "alias", None)
        if isinstance(alias, str) and alias in {"noAlias", "alias", "negatedAlias"}:
            entry["alias"] = alias
        elif alias is not None and not isinstance(alias, str):
            alias_name = getattr(alias, "name", None)
            if isinstance(alias_name, str) and alias_name.strip():
                entry["aliasOf"] = alias_name.strip()[:512]
        raw_aliases = getattr(var, "aliases", None)
        if raw_aliases:
            aliases = []
            for raw_alias in raw_aliases:
                alias_name = _normalize_xml_value(getattr(raw_alias, "name", None))
                if not alias_name:
                    continue
                alias_entry = {"name": alias_name[:512]}
                for attribute, maximum_length in (("description", 4096), ("displayUnit", 256)):
                    value = _normalize_xml_value(getattr(raw_alias, attribute, None))
                    if value:
                        alias_entry[attribute] = value[:maximum_length]
                aliases.append(alias_entry)
            if aliases:
                entry["aliases"] = aliases
        if hasattr(var, "initial") and var.initial:
            entry["initial"] = var.initial
        reinit = getattr(var, "reinit", None)
        if isinstance(reinit, bool):
            entry["reinit"] = reinit
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
        else:
            declared_nominal = getattr(declared_type, "nominal", None)
            if declared_nominal is not None:
                entry["nominal"] = declared_nominal
        for attribute in ("mimeType", "maxSize"):
            value = getattr(var, attribute, None)
            if value is None:
                value = getattr(declared_type, attribute, None)
            if attribute == "mimeType":
                normalized_mime_type = _normalize_xml_value(value)
                if normalized_mime_type:
                    entry[attribute] = normalized_mime_type[:256]
            else:
                normalized_max_size = _finite_fmi_number(value, integer=True)
                if normalized_max_size is not None and normalized_max_size >= 0:
                    entry[attribute] = normalized_max_size
        for attribute in ("relativeQuantity", "unbounded"):
            variable_value = _normalize_fmi_boolean(getattr(var, attribute, None))
            declared_value = _normalize_fmi_boolean(getattr(declared_type, attribute, None))
            if variable_value is True or declared_value is True:
                entry[attribute] = True
            elif variable_value is not None:
                entry[attribute] = variable_value
            elif declared_value is not None:
                entry[attribute] = declared_value
        for attribute in (
            "canBeDeactivated", "priority", "intervalDecimal", "shiftDecimal", "supportsFraction",
            "resolution", "intervalCounter", "shiftCounter",
        ):
            value = getattr(var, attribute, None)
            if value is None:
                value = getattr(declared_type, attribute, None)
            if attribute in {"canBeDeactivated", "supportsFraction"}:
                normalized_value = _normalize_fmi_boolean(value)
            elif attribute in {"intervalDecimal", "shiftDecimal"}:
                normalized_value = _finite_fmi_number(value)
            else:
                normalized_value = _finite_fmi_number(value, integer=True)
            if normalized_value is not None and (
                attribute in {"canBeDeactivated", "supportsFraction", "intervalDecimal", "shiftDecimal"}
                or normalized_value >= 0
            ):
                entry[attribute] = normalized_value
        if declared_type is not None and getattr(declared_type, "name", None):
            declared_type_entry = {
                "name": declared_type.name,
                "type": str(getattr(declared_type, "type", None) or var.type),
            }
            if getattr(declared_type, "description", None):
                declared_type_entry["description"] = declared_type.description
            for attribute in (
                "unit", "quantity", "displayUnit", "min", "max", "nominal",
                "relativeQuantity", "unbounded", "mimeType", "maxSize",
                "intervalVariability", "intervalDecimal", "shiftDecimal", "supportsFraction",
                "resolution", "intervalCounter", "shiftCounter", "canBeDeactivated", "priority",
            ):
                value = getattr(declared_type, attribute, None)
                if value is not None:
                    declared_type_entry[attribute] = value
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
            "needsExecutionTool", "canBeInstantiatedOnlyOncePerProcess", "canNotUseMemoryManagementFunctions",
            "canGetAndSetFMUstate", "canSerializeFMUstate", "canHandleVariableCommunicationStepSize",
            "canInterpolateInputs", "canRunAsynchronuously", "hasEventMode", "providesIntermediateUpdate",
            "canReturnEarlyAfterIntermediateUpdate", "providesEvaluateDiscreteStates",
            "providesDirectionalDerivative", "providesAdjointDerivatives", "providesPerElementDependencies",
            "needsCompletedIntegratorStep",
        ):
            value = getattr(interface, attribute, None)
            if value is not None:
                capabilities[attribute] = bool(value)
        for attribute in ("maxOutputDerivativeOrder", "recommendedIntermediateInputSmoothness"):
            value = getattr(interface, attribute, None)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                capabilities[attribute] = value
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
            # Preserve the presence of BaseUnit even for dimensionless units,
            # whose valid representation is an empty BaseUnit element.
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
            inverse_map = display_unit_inverses or {}
            if inverse_map.get((unit.name, display_unit.name), False):
                display_entry["inverse"] = True
            display_units.append(display_entry)
        if display_units:
            unit_entry["displayUnits"] = display_units
        unit_definitions.append(unit_entry)

    type_definitions: list = []
    for declared_type in getattr(md, "typeDefinitions", []) or []:
        type_name = _normalize_xml_value(getattr(declared_type, "name", None))
        type_kind = _normalize_xml_value(getattr(declared_type, "type", None))
        if not type_name or not type_kind:
            continue
        type_entry: dict[str, Any] = {"name": type_name, "type": type_kind}
        for attribute, maximum_length in (
            ("description", 4096), ("unit", 128), ("quantity", 256), ("displayUnit", 256),
            ("mimeType", 256), ("intervalVariability", 32),
        ):
            value = _normalize_xml_value(getattr(declared_type, attribute, None))
            if value:
                type_entry[attribute] = value[:maximum_length]
        for attribute in ("min", "max", "nominal", "intervalDecimal", "shiftDecimal"):
            value = getattr(declared_type, attribute, None)
            if value is None:
                continue
            number = _finite_fmi_number(value, integer=type_kind in integer_types)
            if number is not None:
                type_entry[attribute] = number
        max_size = _finite_fmi_number(getattr(declared_type, "maxSize", None), integer=True)
        if max_size is not None and max_size >= 0:
            type_entry["maxSize"] = max_size
        for attribute in ("relativeQuantity", "unbounded", "supportsFraction", "canBeDeactivated"):
            value = _normalize_fmi_boolean(getattr(declared_type, attribute, None))
            if value is not None:
                type_entry[attribute] = value
        for attribute in ("resolution", "intervalCounter", "shiftCounter", "priority"):
            value = getattr(declared_type, attribute, None)
            normalized_value = _finite_fmi_number(value, integer=True)
            if normalized_value is not None and normalized_value >= 0:
                type_entry[attribute] = normalized_value
        items = []
        for item in getattr(declared_type, "items", []) or []:
            item_name = _normalize_xml_value(getattr(item, "name", None))
            item_value = getattr(item, "value", None)
            if not item_name or item_value is None:
                continue
            normalized_item = {"name": item_name[:256], "value": str(item_value)}
            item_description = _normalize_xml_value(getattr(item, "description", None))
            if item_description:
                normalized_item["description"] = item_description[:1024]
            items.append(normalized_item)
        if items:
            type_entry["items"] = items
        type_definitions.append(type_entry)

    def describe_model_structure(unknowns, *, include_state_reference=False):
        entries = []
        for unknown in unknowns or []:
            variable = getattr(unknown, "variable", None)
            reference = getattr(variable, "valueReference", None)
            if isinstance(reference, bool) or not isinstance(reference, int) or reference < 0:
                continue
            entry: dict[str, Any] = {"valueReference": reference}
            variable_name = getattr(variable, "name", None)
            if isinstance(variable_name, str) and variable_name:
                entry["name"] = variable_name
            if include_state_reference:
                state_variable = getattr(variable, "derivative", None)
                state_reference = getattr(state_variable, "valueReference", None)
                if isinstance(state_reference, int) and not isinstance(state_reference, bool) and state_reference >= 0:
                    entry["stateValueReference"] = state_reference
                    state_name = getattr(state_variable, "name", None)
                    if isinstance(state_name, str) and state_name:
                        entry["stateName"] = state_name
            dependencies = []
            dependency_names = []
            for dependency in getattr(unknown, "dependencies", None) or []:
                dependency_reference = getattr(dependency, "valueReference", None)
                if isinstance(dependency_reference, int) and not isinstance(dependency_reference, bool) and dependency_reference >= 0:
                    dependencies.append(dependency_reference)
                    dependency_name = getattr(dependency, "name", None)
                    if isinstance(dependency_name, str) and dependency_name:
                        dependency_names.append(dependency_name)
            if dependencies:
                entry["dependencies"] = dependencies
                if len(dependency_names) == len(dependencies):
                    entry["dependencyNames"] = dependency_names
                kinds = list(getattr(unknown, "dependenciesKind", None) or [])
                if len(kinds) == len(dependencies):
                    entry["dependenciesKind"] = kinds
            entries.append(entry)
        return entries

    model_structure = {
        "outputs": describe_model_structure(getattr(md, "outputs", None)),
        "derivatives": describe_model_structure(getattr(md, "derivatives", None), include_state_reference=True),
        "clockedStates": describe_model_structure(getattr(md, "clockedStates", None)),
        "initialUnknowns": describe_model_structure(getattr(md, "initialUnknowns", None)),
        "eventIndicators": describe_model_structure(getattr(md, "eventIndicators", None)),
    }
    model_exchange_capabilities = {}
    model_exchange = getattr(md, "modelExchange", None)
    if model_exchange is not None:
        for attribute in (
            "needsExecutionTool", "canBeInstantiatedOnlyOncePerProcess", "canNotUseMemoryManagementFunctions",
            "canGetAndSetFMUstate", "canSerializeFMUstate", "providesDirectionalDerivative",
            "providesAdjointDerivatives", "completedIntegratorStepNotNeeded", "needsCompletedIntegratorStep",
        ):
            value = getattr(model_exchange, attribute, None)
            if value is not None:
                model_exchange_capabilities[attribute] = bool(value)

    return {
        "modelName": _normalize_xml_value(getattr(md, "modelName", None)) or "DecentraLabsProxy",
        "guid": _normalize_xml_value(getattr(md, "guid", None)),
        "instantiationToken": _normalize_xml_value(getattr(md, "instantiationToken", None)),
        "fmiVersion": md.fmiVersion,
        "simulationKind": simulation_kind,
        "simulationType": simulation_type,
        "executionInterface": simulation_type if simulation_type in {"CoSimulation", "ModelExchange"} else None,
        "supportsCoSimulation": supports_cs,
        "supportsModelExchange": supports_me,
        "supportsExecution": supports_cs or supports_me,
        "defaultStartTime": default_start,
        "defaultStopTime": default_stop,
        "defaultStepSize": default_step,
        "defaultTolerance": default_tolerance,
        "numberOfContinuousStates": int(getattr(md, "numberOfContinuousStates", 0) or 0),
        "numberOfEventIndicators": int(getattr(md, "numberOfEventIndicators", 0) or 0),
        **({"modelStructure": model_structure} if supports_me else {}),
        **({"modelExchangeCapabilities": model_exchange_capabilities} if model_exchange_capabilities else {}),
        "modelVariables": variables,
        "description": _normalize_xml_value(getattr(md, "description", None)) or "",
        "author": _normalize_xml_value(getattr(md, "author", None)) or "",
        "version": _normalize_xml_value(getattr(md, "version", None)) or "",
        "copyright": _normalize_xml_value(getattr(md, "copyright", None)) or "",
        "license": _normalize_xml_value(getattr(md, "license", None)) or "",
        "generationTool": _normalize_xml_value(getattr(md, "generationTool", None)) or "",
        "generationDateAndTime": _normalize_xml_value(getattr(md, "generationDateAndTime", None)) or "",
        "variableNamingConvention": _normalize_xml_value(getattr(md, "variableNamingConvention", None)) or "",
        "capabilities": capabilities,
        "unitDefinitions": unit_definitions,
        "typeDefinitions": type_definitions,
    }


def _public_model_metadata(metadata: dict) -> dict:
    def exact_json_integer(value):
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) > (2**53 - 1):
            return str(value)
        return value

    supports_execution = metadata.get("supportsExecution")
    if not isinstance(supports_execution, bool):
        supports_execution = bool(metadata.get("supportsCoSimulation") or metadata.get("supportsModelExchange"))

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
            "valueReference", "alias", "aliasOf", "aliases", "initial", "reinit", "intervalVariability", "unit", "start", "min", "max", "dimensions",
            "description", "displayName", "displayUnit", "enumItems", "nominal",
            "quantity", "declaredType", "mimeType", "maxSize", "relativeQuantity", "unbounded",
            "canBeDeactivated", "priority", "intervalDecimal", "shiftDecimal", "supportsFraction",
            "resolution", "intervalCounter", "shiftCounter",
        ):
            if optional_key in variable:
                entry[optional_key] = variable[optional_key]
        integer_type = str(variable.get("type", "")).lower() in {
            "integer", "enumeration", "int8", "uint8", "int16", "uint16",
            "int32", "uint32", "int64", "uint64",
        }
        if integer_type:
            for field in ("min", "max"):
                if field in entry:
                    entry[field] = exact_json_integer(entry[field])
        for field in ("maxSize", "resolution", "intervalCounter", "shiftCounter"):
            if field in entry:
                entry[field] = exact_json_integer(entry[field])
        if isinstance(entry.get("dimensions"), list):
            entry["dimensions"] = [
                {
                    **dimension,
                    **({"start": exact_json_integer(dimension["start"])} if "start" in dimension else {}),
                }
                for dimension in entry["dimensions"]
                if isinstance(dimension, dict)
            ]
        if isinstance(entry.get("enumItems"), list):
            entry["enumItems"] = [
                {**item, "value": exact_json_integer(item.get("value"))}
                for item in entry["enumItems"]
                if isinstance(item, dict)
            ]
        declared_type = entry.get("declaredType")
        if isinstance(declared_type, dict):
            declared_type = dict(declared_type)
            declared_type_name = str(declared_type.get("type", variable.get("type", ""))).lower()
            if declared_type_name in {
                "integer", "enumeration", "int8", "uint8", "int16", "uint16",
                "int32", "uint32", "int64", "uint64",
            }:
                for field in ("min", "max"):
                    if field in declared_type:
                        declared_type[field] = exact_json_integer(declared_type[field])
            for field in ("maxSize", "resolution", "intervalCounter", "shiftCounter"):
                if field in declared_type:
                    declared_type[field] = exact_json_integer(declared_type[field])
            entry["declaredType"] = declared_type
        variables.append(entry)

    payload = {
        "fmiVersion": metadata.get("fmiVersion", "2.0"),
        "simulationKind": metadata.get("simulationKind", "unknown"),
        "simulationType": metadata.get("simulationType", "Unknown"),
        "executionInterface": metadata.get("executionInterface"),
        "supportsExecution": supports_execution,
        "supportsCoSimulation": bool(metadata.get("supportsCoSimulation")),
        "supportsModelExchange": bool(metadata.get("supportsModelExchange")),
        "availableExecutionInterfaces": list(metadata.get("availableExecutionInterfaces") or []),
        "supportsFmiLsDae": bool(metadata.get("supportsFmiLsDae")),
        "modelVariables": variables,
    }
    fmi_ls_dae = metadata.get("fmiLsDae")
    if isinstance(fmi_ls_dae, dict):
        # The proxy needs this bounded declaration to expose the selector with
        # legal Configuration/Reconfiguration write phases. Keep the equation
        # names summary already used by Gateway, but do not expose the manifest.
        payload["fmiLsDae"] = {
            "manifestName": fmi_ls_dae.get("manifestName"),
            "manifestVersion": fmi_ls_dae.get("manifestVersion"),
            "enableDAEParameter": fmi_ls_dae.get("enableDAEParameter"),
            "algebraicVariables": fmi_ls_dae.get("algebraicVariables"),
            "residualVariableCount": fmi_ls_dae.get("residualVariableCount"),
        }
    model_name = metadata.get("modelName")
    if isinstance(model_name, str) and model_name.strip():
        payload["modelName"] = model_name.strip()[:256]
    for key in ("defaultStartTime", "defaultStopTime", "defaultStepSize", "defaultTolerance"):
        if metadata.get(key) is not None:
            payload[key] = float(metadata[key])
    for key in ("numberOfContinuousStates", "numberOfEventIndicators"):
        value = metadata.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            payload[key] = value
    for key in (
        "description", "author", "version", "copyright", "license",
        "generationTool", "generationDateAndTime",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            payload[key] = value.strip()[:4096]
    variable_naming_convention = metadata.get("variableNamingConvention")
    if variable_naming_convention in {"flat", "structured"}:
        payload["variableNamingConvention"] = variable_naming_convention
    unit_definitions = metadata.get("unitDefinitions")
    if isinstance(unit_definitions, list):
        payload["unitDefinitions"] = unit_definitions
    type_definitions = metadata.get("typeDefinitions")
    if isinstance(type_definitions, list):
        exact_type_definitions = []
        for raw_type in type_definitions:
            if not isinstance(raw_type, dict):
                continue
            declared_type = dict(raw_type)
            type_name = str(declared_type.get("type", "")).lower()
            if type_name in {
                "integer", "enumeration", "int8", "uint8", "int16", "uint16",
                "int32", "uint32", "int64", "uint64",
            }:
                for field in ("min", "max"):
                    if field in declared_type:
                        declared_type[field] = exact_json_integer(declared_type[field])
            for field in ("maxSize", "resolution", "intervalCounter", "shiftCounter"):
                if field in declared_type:
                    declared_type[field] = exact_json_integer(declared_type[field])
            if isinstance(declared_type.get("items"), list):
                declared_type["items"] = [
                    {**item, "value": exact_json_integer(item.get("value"))}
                    for item in declared_type["items"]
                    if isinstance(item, dict)
                ]
            exact_type_definitions.append(declared_type)
        payload["typeDefinitions"] = exact_type_definitions
    raw_capabilities = metadata.get("capabilities")
    if isinstance(raw_capabilities, dict):
        public_capabilities = {}
        for name in (
            "needsExecutionTool", "canBeInstantiatedOnlyOncePerProcess", "canNotUseMemoryManagementFunctions",
            "canGetAndSetFMUstate", "canSerializeFMUstate", "canHandleVariableCommunicationStepSize",
            "canInterpolateInputs", "canRunAsynchronuously", "hasEventMode", "providesIntermediateUpdate",
            "canReturnEarlyAfterIntermediateUpdate", "providesEvaluateDiscreteStates",
            "providesDirectionalDerivative", "providesAdjointDerivatives", "providesPerElementDependencies",
            "needsCompletedIntegratorStep",
        ):
            value = raw_capabilities.get(name)
            if isinstance(value, bool):
                public_capabilities[name] = value
        for name in ("maxOutputDerivativeOrder", "recommendedIntermediateInputSmoothness"):
            value = raw_capabilities.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                public_capabilities[name] = value
        fixed_step = raw_capabilities.get("fixedInternalStepSize")
        if fixed_step is not None:
            try:
                fixed_step_value = float(fixed_step)
            except (TypeError, ValueError, OverflowError):
                fixed_step_value = 0.0
            if math.isfinite(fixed_step_value) and fixed_step_value > 0:
                public_capabilities["fixedInternalStepSize"] = fixed_step_value
        if public_capabilities:
            payload["capabilities"] = public_capabilities
    if metadata.get("instantiationToken"):
        payload["instantiationToken"] = metadata["instantiationToken"]
    fmi_ls_struct = None
    if str(metadata.get("fmiVersion") or "").split(".", 1)[0] == "3":
        fmi_ls_struct = normalize_fmi_ls_struct(
            metadata.get("fmiLsStruct"),
            variable_names=[variable["name"] for variable in variables if isinstance(variable.get("name"), str)],
        )
    if fmi_ls_struct is not None:
        payload["fmiLsStruct"] = fmi_ls_struct
    return payload
