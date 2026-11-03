from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree as ET

from fastapi import HTTPException

from metadata import (
    _collect_declared_type_definitions,
    _format_fmi3_binary_start_value,
    _format_fmi_start_value,
    _normalize_proxy_fmi3_type,
    _normalize_xml_value,
    _parse_fmi_major_version,
)


def _flatten_fmi_start_values(value):
    """Return FMI array starts in row-major flat order, including array-likes."""
    if hasattr(value, "tolist") and callable(value.tolist):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        flattened = []
        for item in value:
            flattened.extend(_flatten_fmi_start_values(item))
        return flattened
    return [value]


def _proxy_model_identifier(model_metadata: dict) -> str:
    # Keep a stable identifier so the native runtime binary name stays generic.
    return "decentralabs_proxy"


def _append_proxy_type_definitions(root, model_metadata: dict, fmi_major_version: int) -> set[str]:
    definitions = _collect_declared_type_definitions(model_metadata)
    if not definitions:
        return set()

    exported_names: set[str] = set()
    type_definitions = ET.SubElement(root, "TypeDefinitions")
    fmi2_tags = {
        "Real": "Real", "Integer": "Integer", "Boolean": "Boolean",
        "String": "String", "Enumeration": "Enumeration",
    }
    fmi3_tags = {
        "Float32": "Float32Type", "Float64": "Float64Type",
        "Int8": "Int8Type", "UInt8": "UInt8Type", "Int16": "Int16Type",
        "UInt16": "UInt16Type", "Int32": "Int32Type", "UInt32": "UInt32Type",
        "Int64": "Int64Type", "UInt64": "UInt64Type", "Boolean": "BooleanType",
        "String": "StringType", "Binary": "BinaryType", "Enumeration": "EnumerationType",
        "Clock": "ClockType",
    }

    for type_name in sorted(definitions):
        declared_type = definitions[type_name]
        declared_type_name = str(declared_type.get("type") or "")
        if fmi_major_version >= 3 and declared_type_name == "Integer":
            declared_type_name = "Int32"
        type_tag = (fmi3_tags if fmi_major_version >= 3 else fmi2_tags).get(declared_type_name)
        if type_tag is None:
            continue

        description = _normalize_xml_value(declared_type.get("description"))
        attrs = {"name": type_name}
        if description:
            attrs["description"] = description
        if fmi_major_version < 3:
            definition_element = ET.SubElement(type_definitions, "SimpleType", attrs)
            typed_element = ET.SubElement(definition_element, type_tag)
            if declared_type_name == "Real":
                for field in ("unit", "displayUnit", "quantity"):
                    value = _normalize_xml_value(declared_type.get(field))
                    if value:
                        typed_element.set(field, value)
                for field in ("min", "max", "nominal"):
                    value = declared_type.get(field)
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                        typed_element.set(field, format(value, ".17g"))
                for field in ("relativeQuantity", "unbounded"):
                    value = declared_type.get(field)
                    if isinstance(value, bool):
                        typed_element.set(field, str(value).lower())
            elif declared_type_name == "Integer":
                quantity = _normalize_xml_value(declared_type.get("quantity"))
                if quantity:
                    typed_element.set("quantity", quantity)
                for field in ("min", "max"):
                    value = declared_type.get(field)
                    if isinstance(value, int) and not isinstance(value, bool):
                        typed_element.set(field, str(value))
            elif declared_type_name == "Enumeration":
                quantity = _normalize_xml_value(declared_type.get("quantity"))
                if quantity:
                    typed_element.set("quantity", quantity)
                _append_enumeration_items(typed_element, declared_type, minimum=-(2**31), maximum=(2**31) - 1)
        else:
            attrs_to_copy = []
            if declared_type_name in {"Float32", "Float64"}:
                attrs_to_copy.extend(("unit", "displayUnit", "quantity", "relativeQuantity", "unbounded"))
                attrs_to_copy.extend(("min", "max", "nominal"))
            elif declared_type_name in {
                "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64",
                "Enumeration", "Integer",
            }:
                attrs_to_copy.extend(("quantity", "min", "max"))
            elif declared_type_name == "Binary":
                attrs_to_copy.extend(("mimeType", "maxSize"))
            elif declared_type_name == "Clock":
                attrs_to_copy.extend((
                    "canBeDeactivated", "priority", "intervalVariability", "intervalDecimal",
                    "shiftDecimal", "supportsFraction", "resolution", "intervalCounter", "shiftCounter",
                ))
            typed_attrs = dict(attrs)
            for field in attrs_to_copy:
                value = declared_type.get(field)
                if isinstance(value, bool):
                    typed_attrs[field] = str(value).lower()
                elif field in {"min", "max", "nominal", "intervalDecimal", "shiftDecimal"}:
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                        typed_attrs[field] = str(int(value)) if field in {"min", "max"} and declared_type_name not in {"Float32", "Float64"} else format(value, ".17g")
                elif field == "maxSize" or field in {"priority", "resolution", "intervalCounter", "shiftCounter"}:
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        typed_attrs[field] = str(value)
                else:
                    normalized = _normalize_xml_value(value)
                    if normalized:
                        typed_attrs[field] = normalized
            typed_element = ET.SubElement(type_definitions, type_tag, typed_attrs)
            if declared_type_name == "Enumeration":
                _append_enumeration_items(typed_element, declared_type, minimum=-(2**63), maximum=(2**63) - 1)
        exported_names.add(type_name)

    if not exported_names:
        root.remove(type_definitions)
    return exported_names


def _append_enumeration_items(parent, declared_type: dict[str, Any], *, minimum: int, maximum: int) -> None:
    for item in declared_type.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        raw_value = item.get("value")
        if raw_value is None:
            continue
        try:
            value = int(raw_value)
        except (TypeError, ValueError, OverflowError):
            continue
        name = _normalize_xml_value(item.get("name"))
        if name is None or not minimum <= value <= maximum:
            continue
        attrs = {"name": name, "value": str(value)}
        description = _normalize_xml_value(item.get("description"))
        if description:
            attrs["description"] = description
        ET.SubElement(parent, "Item", attrs)


def _validate_declared_type_references(model_metadata: dict, fmi_major_version: int) -> None:
    definitions = _collect_declared_type_definitions(model_metadata)
    for variable in model_metadata.get("modelVariables", []):
        if fmi_major_version >= 3 and variable.get("aliasOf"):
            continue
        variable_type = str(variable.get("type") or "Real")
        declared_type = variable.get("declaredType") if isinstance(variable.get("declaredType"), dict) else {}
        type_name = _normalize_xml_value(declared_type.get("name"))
        must_have_type = variable_type == "Enumeration"
        if not type_name:
            if must_have_type:
                raise HTTPException(
                    status_code=422,
                    detail=f"Enumeration variable is missing its FMI declared type: {variable.get('name')}",
                )
            continue
        definition = definitions.get(type_name)
        if definition is None:
            raise HTTPException(
                status_code=422,
                detail=f"FMI declared type is not defined: {type_name}",
            )
        definition_type = str(definition.get("type") or "")
        expected_type = _normalize_proxy_fmi3_type(variable_type) if fmi_major_version >= 3 else variable_type
        actual_type = _normalize_proxy_fmi3_type(definition_type) if fmi_major_version >= 3 else definition_type
        if expected_type != actual_type:
            raise HTTPException(
                status_code=422,
                detail=f"FMI declared type {type_name} does not match variable type {variable_type}",
            )
        if fmi_major_version >= 3 and expected_type == "Clock":
            interval_variability = definition.get("intervalVariability")
            if interval_variability not in {"constant", "fixed", "tunable", "changing", "countdown", "triggered"}:
                raise HTTPException(
                    status_code=422,
                    detail=f"FMI Clock type is missing a valid intervalVariability: {type_name}",
                )
        if variable_type == "Enumeration":
            items = definition.get("items")
            if not isinstance(items, list) or not items:
                raise HTTPException(
                    status_code=422,
                    detail=f"FMI enumeration type has no items: {type_name}",
                )
            seen_names: set[str] = set()
            seen_values: set[int] = set()
            minimum, maximum = (-(2**31), (2**31) - 1) if fmi_major_version < 3 else (-(2**63), (2**63) - 1)
            for item in items:
                if not isinstance(item, dict):
                    raise HTTPException(status_code=422, detail=f"FMI enumeration type is malformed: {type_name}")
                item_name = _normalize_xml_value(item.get("name"))
                raw_item_value = item.get("value")
                if raw_item_value is None:
                    raise HTTPException(status_code=422, detail=f"FMI enumeration type is malformed: {type_name}")
                try:
                    item_value = int(raw_item_value)
                except (TypeError, ValueError, OverflowError):
                    item_name = None
                    item_value = minimum - 1
                if (
                    not item_name
                    or item_name in seen_names
                    or item_value in seen_values
                    or not minimum <= item_value <= maximum
                ):
                    raise HTTPException(status_code=422, detail=f"FMI enumeration type is malformed: {type_name}")
                seen_names.add(item_name)
                seen_values.add(item_value)


def _execution_interfaces_for_proxy(model_metadata: dict) -> tuple[list[str], list[str]]:
    available_interfaces = model_metadata.get("availableExecutionInterfaces")
    if not isinstance(available_interfaces, list):
        available_interfaces = [
            name for name, supported in (
                ("CoSimulation", model_metadata.get("supportsCoSimulation") is True),
                ("ModelExchange", model_metadata.get("supportsModelExchange") is True),
            ) if supported
        ]
    if "authorizedExecutionInterfaces" not in model_metadata:
        authorized_interfaces = ["CoSimulation"] if "CoSimulation" in available_interfaces else list(available_interfaces)
    else:
        authorized_interfaces = model_metadata.get("authorizedExecutionInterfaces")
        if not isinstance(authorized_interfaces, list) or not authorized_interfaces:
            raise HTTPException(status_code=422, detail="Authorized FMI execution interfaces are invalid")
    return available_interfaces, authorized_interfaces


def _validate_proxy_generation_supported(model_metadata: dict):
    available_interfaces, authorized_interfaces = _execution_interfaces_for_proxy(model_metadata)
    if (
        any(name not in {"CoSimulation", "ModelExchange"} for name in available_interfaces)
        or any(name not in available_interfaces for name in authorized_interfaces)
        or len(authorized_interfaces) != len(set(authorized_interfaces))
        or not authorized_interfaces
    ):
        raise HTTPException(status_code=422, detail="Authorized FMI execution interfaces do not match the source FMU")
    fmi_major_version = _parse_fmi_major_version(model_metadata.get("fmiVersion"))
    if not available_interfaces or fmi_major_version not in {2, 3}:
        raise HTTPException(
            status_code=422,
            detail="Generated proxy FMUs require an executable FMI 2 or FMI 3 Co-Simulation or Model Exchange source",
        )
    if "ModelExchange" in authorized_interfaces:
        model_structure = model_metadata.get("modelStructure")
        if not isinstance(model_structure, dict):
            raise HTTPException(status_code=422, detail="Model Exchange proxy requires the source FMI ModelStructure")
        if (
            isinstance(model_metadata.get("numberOfContinuousStates"), bool)
            or not isinstance(model_metadata.get("numberOfContinuousStates"), int)
            or model_metadata["numberOfContinuousStates"] < 0
            or isinstance(model_metadata.get("numberOfEventIndicators"), bool)
            or not isinstance(model_metadata.get("numberOfEventIndicators"), int)
            or model_metadata["numberOfEventIndicators"] < 0
        ):
            raise HTTPException(status_code=422, detail="Model Exchange proxy requires valid state and event counts")
        derivatives = model_structure.get("derivatives")
        if not isinstance(derivatives, list):
            raise HTTPException(status_code=422, detail="Model Exchange proxy requires ordered derivative metadata")
        variables = model_metadata.get("modelVariables")
        references = {
            variable.get("valueReference")
            for variable in variables or []
            if isinstance(variable, dict) and isinstance(variable.get("valueReference"), int)
            and not isinstance(variable.get("valueReference"), bool)
        }
        if model_metadata["numberOfContinuousStates"] > 0 and not derivatives:
            raise HTTPException(status_code=422, detail="Model Exchange proxy has states but no ordered derivatives")
        for derivative in derivatives:
            if (
                not isinstance(derivative, dict)
                or derivative.get("valueReference") not in references
                or isinstance(derivative.get("stateValueReference"), bool)
                or not isinstance(derivative.get("stateValueReference"), int)
                or derivative["stateValueReference"] not in references
            ):
                raise HTTPException(status_code=422, detail="Model Exchange proxy requires derivative-to-state mappings")
    _validate_declared_type_references(model_metadata, fmi_major_version)
    if fmi_major_version < 3:
        return

    source_capabilities = model_metadata.get("capabilities")
    source_capabilities = source_capabilities if isinstance(source_capabilities, dict) else {}
    has_clock = False
    source_uses_model_exchange = "ModelExchange" in authorized_interfaces
    model_variables = model_metadata.get("modelVariables", [])
    variables_by_reference = {
        variable.get("valueReference"): variable
        for variable in model_variables
        if isinstance(variable, dict) and variable.get("valueReference") is not None
    }
    supported_types = {
        "Float32",
        "Float64",
        "Int8",
        "UInt8",
        "Int16",
        "UInt16",
        "Int32",
        "UInt32",
        "Int64",
        "UInt64",
        "Boolean",
        "String",
        "Binary",
        "Clock",
        "Enumeration",
    }
    for variable in model_variables:
        normalized_type = _normalize_proxy_fmi3_type(variable.get("type"))
        if normalized_type not in supported_types:
            raise HTTPException(
                status_code=422,
                detail=f"Generated FMI 3 proxy FMUs do not yet support variable type: {variable.get('type')}",
            )
        if normalized_type == "Clock" and (variable.get("dimensions") or []):
            raise HTTPException(
                status_code=422,
                detail=f"Generated FMI 3 proxy FMUs do not yet support dimensioned Clock variables: {variable.get('name')}",
            )
        if normalized_type == "Clock":
            has_clock = True
            if (
                variable.get("causality") not in {"input", "output"}
                or variable.get("intervalVariability") != "triggered"
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"Generated FMI 3 proxy FMUs currently support only triggered input and output Clocks: {variable.get('name')}",
                )
        if variable.get("causality") == "structuralParameter":
            if variable.get("variability") not in {"fixed", "tunable"}:
                raise HTTPException(
                    status_code=422,
                    detail=f"FMI structural parameters must be fixed or tunable: {variable.get('name')}",
                )
        for dimension in variable.get("dimensions", []) or []:
            if "start" not in dimension and "valueReference" not in dimension:
                raise HTTPException(
                    status_code=422,
                    detail=f"Generated FMI 3 proxy FMUs require dimension metadata for variable: {variable.get('name')}",
                )
            if "valueReference" in dimension:
                structural_parameter = variables_by_reference.get(dimension.get("valueReference"))
                if (
                    not isinstance(structural_parameter, dict)
                    or _normalize_proxy_fmi3_type(structural_parameter.get("type")) != "UInt64"
                    or not (
                        structural_parameter.get("variability") == "constant"
                        or (
                            structural_parameter.get("causality") == "structuralParameter"
                            and structural_parameter.get("variability") in {"fixed", "tunable"}
                        )
                    )
                    or (structural_parameter.get("causality") == "structuralParameter"
                        and structural_parameter.get("dimensions"))
                ):
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Generated FMI 3 proxy FMUs require dimensions to reference constant or "
                            f"fixed/tunable structural UInt64 variables: {variable.get('name')}"
                        ),
                    )
    if has_clock and not source_uses_model_exchange and source_capabilities.get("hasEventMode") is not True:
        raise HTTPException(
            status_code=422,
            detail="Generated FMI 3 proxy FMUs require source Event Mode support for Clock variables",
        )


def _build_proxy_model_description_xml(model_metadata: dict) -> bytes:
    _validate_proxy_generation_supported(model_metadata)

    model_name = _normalize_xml_value(model_metadata.get("modelName")) or "DecentraLabsProxy"
    guid = _normalize_xml_value(model_metadata.get("guid")) or "{" + uuid4().hex + "}"
    instantiation_token = _normalize_xml_value(model_metadata.get("instantiationToken")) or guid
    model_identifier = _proxy_model_identifier(model_metadata)
    fmi_major_version = _parse_fmi_major_version(model_metadata.get("fmiVersion"))
    source_capabilities = model_metadata.get("capabilities")
    source_capabilities = source_capabilities if isinstance(source_capabilities, dict) else {}
    can_get_and_set_fmu_state = any(
        source_capabilities.get(name) is True
        for name in ("canGetAndSetFMUstate", "canGetAndSetFMUState")
    )
    can_serialize_fmu_state = any(
        source_capabilities.get(name) is True
        for name in ("canSerializeFMUstate", "canSerializeFMUState")
    )
    supports_serializable_fmu_state = can_get_and_set_fmu_state and can_serialize_fmu_state
    available_interfaces, authorized_interfaces = _execution_interfaces_for_proxy(model_metadata)
    supports_co_simulation = "CoSimulation" in authorized_interfaces
    supports_model_exchange = "ModelExchange" in authorized_interfaces
    can_handle_variable_communication_step_size = supports_model_exchange or any(
        source_capabilities.get(name) is True
        for name in (
            "canHandleVariableCommunicationStepSize",
            "canhandlevariablecommunicationstepsize",
        )
    )
    raw_fixed_internal_step_size = None if supports_model_exchange else source_capabilities.get("fixedInternalStepSize")
    fixed_internal_step_size = None
    if isinstance(raw_fixed_internal_step_size, (int, float, str)) and not isinstance(raw_fixed_internal_step_size, bool):
        try:
            parsed_fixed_step_size = float(raw_fixed_internal_step_size)
        except (TypeError, ValueError, OverflowError):
            parsed_fixed_step_size = 0.0
        if math.isfinite(parsed_fixed_step_size) and parsed_fixed_step_size > 0:
            fixed_internal_step_size = format(parsed_fixed_step_size, ".17g")
    declared_units: set[str] = set()
    for variable in model_metadata.get("modelVariables", []):
        if str(variable.get("type", "Real") or "Real") not in {"Real", "Float32", "Float64"}:
            continue
        unit_name = _normalize_xml_value(variable.get("unit"))
        if unit_name is not None:
            declared_units.add(unit_name)

    root_attributes = {
        "modelName": model_name,
        "generationTool": "DecentraLabs FMU Proxy Generator",
        "generationDateAndTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    for attribute in ("description", "author", "version", "copyright", "license"):
        value = _normalize_xml_value(model_metadata.get(attribute))
        if value:
            root_attributes[attribute] = value
    if fmi_major_version >= 3:
        root_attributes["fmiVersion"] = "3.0"
        root_attributes["instantiationToken"] = instantiation_token
        root_attributes["variableNamingConvention"] = model_metadata.get("variableNamingConvention") or "flat"
    else:
        root_attributes.update({
            "fmiVersion": "2.0",
            "guid": guid,
            "variableNamingConvention": model_metadata.get("variableNamingConvention") or "flat",
            "numberOfEventIndicators": str(
                model_metadata.get("numberOfEventIndicators", 0) if supports_model_exchange else 0
            ),
        })
    root = ET.Element("fmiModelDescription", root_attributes)

    if supports_model_exchange:
        raw_me_capabilities = model_metadata.get("modelExchangeCapabilities")
        me_capabilities = raw_me_capabilities if isinstance(raw_me_capabilities, dict) else {}
        if fmi_major_version >= 3:
            me_attributes = {"modelIdentifier": model_identifier}
            for source_name, target_name, default in (
                ("needsExecutionTool", "needsExecutionTool", False),
                ("canBeInstantiatedOnlyOncePerProcess", "canBeInstantiatedOnlyOncePerProcess", False),
                ("canGetAndSetFMUstate", "canGetAndSetFMUState", False),
                ("canSerializeFMUstate", "canSerializeFMUState", False),
                ("providesDirectionalDerivative", "providesDirectionalDerivative", False),
                ("providesAdjointDerivatives", "providesAdjointDerivatives", False),
                ("completedIntegratorStepNotNeeded", "completedIntegratorStepNotNeeded", False),
            ):
                value = me_capabilities.get(source_name, source_capabilities.get(source_name, default))
                if source_name in {"providesDirectionalDerivative", "providesAdjointDerivatives"}:
                    value = False
                me_attributes[target_name] = str(value is True).lower()
        else:
            me_attributes = {"modelIdentifier": model_identifier}
            for source_name in (
                "needsExecutionTool", "canBeInstantiatedOnlyOncePerProcess",
                "canNotUseMemoryManagementFunctions", "canGetAndSetFMUstate",
                "canSerializeFMUstate", "providesDirectionalDerivative",
            ):
                value = me_capabilities.get(source_name, source_capabilities.get(source_name, False))
                if source_name == "providesDirectionalDerivative":
                    value = False
                me_attributes[source_name] = str(value is True).lower()
        ET.SubElement(root, "ModelExchange", me_attributes)

    if fmi_major_version >= 3:
        # A Co-Simulation proxy backed by a Model Exchange source can process
        # importer-initiated input events and structural reconfiguration. The
        # generated CS interface must therefore expose Event Mode even when
        # the source capability document only describes the source ME FMU.
        supports_event_mode = supports_model_exchange or source_capabilities.get("hasEventMode") is True
        co_simulation_attributes = {
            "modelIdentifier": model_identifier,
            "canHandleVariableCommunicationStepSize": str(can_handle_variable_communication_step_size).lower(),
            "canGetAndSetFMUState": str(supports_serializable_fmu_state).lower(),
            "canSerializeFMUState": str(supports_serializable_fmu_state).lower(),
            "hasEventMode": str(supports_event_mode).lower(),
            "mightReturnEarlyFromDoStep": "true",
        }
        if fixed_internal_step_size is not None:
            co_simulation_attributes["fixedInternalStepSize"] = fixed_internal_step_size
        if supports_co_simulation:
            ET.SubElement(root, "CoSimulation", co_simulation_attributes)
    else:
        co_simulation_attributes = {
            "modelIdentifier": model_identifier,
            "canHandleVariableCommunicationStepSize": str(can_handle_variable_communication_step_size).lower(),
            "canInterpolateInputs": "false",
            "maxOutputDerivativeOrder": "0",
            "canRunAsynchronuously": "false",
            "canBeInstantiatedOnlyOncePerProcess": "false",
            "canNotUseMemoryManagementFunctions": "true",
            "canGetAndSetFMUstate": str(supports_serializable_fmu_state).lower(),
            "canSerializeFMUstate": str(supports_serializable_fmu_state).lower(),
            "providesDirectionalDerivative": "false",
        }
        if fixed_internal_step_size is not None:
            co_simulation_attributes["fixedInternalStepSize"] = fixed_internal_step_size
        if supports_co_simulation:
            ET.SubElement(root, "CoSimulation", co_simulation_attributes)

    source_unit_definitions: dict[str, dict[str, Any]] = {}
    for unit in model_metadata.get("unitDefinitions", []):
        if not isinstance(unit, dict):
            continue
        unit_name = unit.get("name")
        if isinstance(unit_name, str) and unit_name:
            source_unit_definitions[unit_name] = unit
    all_unit_names = declared_units | set(source_unit_definitions)
    if all_unit_names:
        unit_definitions = ET.SubElement(root, "UnitDefinitions")
        for unit_name in sorted(all_unit_names):
            source_unit = source_unit_definitions.get(unit_name, {})
            unit_element = ET.SubElement(unit_definitions, "Unit", {"name": unit_name})
            base_unit = source_unit.get("baseUnit")
            if isinstance(base_unit, dict):
                base_attrs = {}
                for exponent in ("kg", "m", "s", "A", "K", "mol", "cd", "rad"):
                    value = base_unit.get(exponent)
                    if isinstance(value, int) and not isinstance(value, bool):
                        base_attrs[exponent] = str(value)
                for field, default in (("factor", 1.0), ("offset", 0.0)):
                    value = base_unit.get(field)
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                        if value != default:
                            base_attrs[field] = format(value, ".17g")
                # Keep an explicitly empty BaseUnit for dimensionless units.
                ET.SubElement(unit_element, "BaseUnit", base_attrs)
            for display_unit in source_unit.get("displayUnits", []) or []:
                if not isinstance(display_unit, dict) or not display_unit.get("name"):
                    continue
                display_attrs = {"name": str(display_unit["name"])}
                for field, default in (("factor", 1.0), ("offset", 0.0)):
                    value = display_unit.get(field)
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                        if value != default:
                            display_attrs[field] = format(value, ".17g")
                if fmi_major_version >= 3 and display_unit.get("inverse") is True:
                    display_attrs["inverse"] = "true"
                ET.SubElement(unit_element, "DisplayUnit", display_attrs)

    exported_declared_type_names = _append_proxy_type_definitions(
        root,
        model_metadata,
        fmi_major_version,
    )

    attrs = {}
    if model_metadata.get("defaultStartTime") is not None:
        attrs["startTime"] = str(model_metadata["defaultStartTime"])
    if model_metadata.get("defaultStopTime") is not None:
        attrs["stopTime"] = str(model_metadata["defaultStopTime"])
    if model_metadata.get("defaultStepSize") is not None:
        attrs["stepSize"] = str(model_metadata["defaultStepSize"])
    if model_metadata.get("defaultTolerance") is not None:
        attrs["tolerance"] = str(model_metadata["defaultTolerance"])
    if attrs:
        ET.SubElement(root, "DefaultExperiment", attrs)

    model_variables = ET.SubElement(root, "ModelVariables")
    output_indexes = []
    initial_unknown_indexes = []
    written_index = 0  # 1-based position in ModelVariables (independent vars excluded)
    written_indexes_by_reference: dict[int, int] = {}
    written_indexes_by_name: dict[str, int] = {}
    proxy_variable_indexes: dict[int, int] = {}
    proxy_variable_index = 0
    for source_index, source_variable in enumerate(model_metadata.get("modelVariables") or [], start=1):
        if not isinstance(source_variable, dict):
            continue
        if fmi_major_version >= 3 and source_variable.get("aliasOf"):
            continue
        if fmi_major_version < 3 and str(source_variable.get("causality") or "").lower() == "independent":
            continue
        proxy_variable_index += 1
        raw_source_reference = source_variable.get("valueReference", source_index)
        if raw_source_reference is None:
            raw_source_reference = source_index
        if type(raw_source_reference) is not int or raw_source_reference < 0:
            continue
        source_reference = raw_source_reference
        proxy_variable_indexes.setdefault(source_reference, proxy_variable_index)
    model_structure = model_metadata.get("modelStructure")
    derivative_state_by_reference: dict[int, int] = {}
    if supports_model_exchange and isinstance(model_structure, dict):
        for derivative in model_structure.get("derivatives", []) or []:
            if not isinstance(derivative, dict):
                continue
            derivative_reference = derivative.get("valueReference")
            state_reference = derivative.get("stateValueReference")
            if type(derivative_reference) is not int or type(state_reference) is not int:
                continue
            derivative_state_by_reference[derivative_reference] = state_reference
    continuous_state_references = set(derivative_state_by_reference.values())

    for index, var in enumerate(model_metadata.get("modelVariables", []), start=1):
        # FMI 3 aliases are emitted as child Alias elements of their primary
        # variable, never as duplicate typed variables with the same reference.
        if fmi_major_version >= 3 and var.get("aliasOf"):
            continue
        # FMI 2: skip independent variables (time) — OpenModelica's FMI2XML parser rejects the
        # modelDescription.xml when an independent variable lacks a start attribute, even though
        # start is N.A. for that causality/variability combination per the FMI 2.0 spec.
        # FMI 3 keeps independent variables because parsers handle them correctly there.
        if fmi_major_version < 3 and (var.get("causality") or "").lower() == "independent":
            continue
        written_index += 1
        var_type = str(var.get("type", "Real") or "Real")
        declared_type = var.get("declaredType") if isinstance(var.get("declaredType"), dict) else {}
        declared_type_name = _normalize_xml_value(declared_type.get("name"))
        raw_value_reference = var.get("valueReference")
        if raw_value_reference is None:
            numeric_reference = index
        elif type(raw_value_reference) is int and raw_value_reference >= 0:
            numeric_reference = raw_value_reference
        else:
            numeric_reference = index
        value_reference = numeric_reference
        written_indexes_by_reference.setdefault(numeric_reference, written_index)
        variable_name = var.get("name")
        if isinstance(variable_name, str) and variable_name:
            written_indexes_by_name.setdefault(variable_name, written_index)
        scalar_attrs = {
            "name": str(var.get("name") or f"var_{index}"),
            "valueReference": str(value_reference),
        }
        state_reference = derivative_state_by_reference.get(numeric_reference)
        if state_reference is not None:
            if fmi_major_version >= 3:
                scalar_attrs["derivative"] = str(state_reference)
            else:
                state_index = proxy_variable_indexes.get(state_reference)
                if state_index is None:
                    raise HTTPException(status_code=422, detail="FMI 2 derivative references an unexported state variable")
                scalar_attrs["derivative"] = str(state_index)
        variable_description = _normalize_xml_value(var.get("description"))
        if variable_description:
            scalar_attrs["description"] = variable_description
        # Alias metadata is retained in the Gateway/AAS metadata extension.
        # FMI 2.0 ScalarVariable has no `alias` attribute, so it must not be
        # copied into the standard modelDescription XML.
        causality = _normalize_xml_value(var.get("causality"))
        variability = _normalize_xml_value(var.get("variability"))
        normalized_fmi3_type = _normalize_proxy_fmi3_type(var_type)
        initial = _normalize_xml_value(var.get("initial"))
        if causality:
            scalar_attrs["causality"] = causality
        if variability:
            scalar_attrs["variability"] = variability
        if initial and not (fmi_major_version >= 3 and normalized_fmi3_type == "Clock"):
            scalar_attrs["initial"] = initial

        type_attrs = {}
        if fmi_major_version >= 3 and normalized_fmi3_type != "Clock":
            clock_references = [
                str(reference)
                for reference in (var.get("clocks") or [])
                if isinstance(reference, int) and not isinstance(reference, bool) and reference >= 0
            ]
            if clock_references:
                type_attrs["clocks"] = " ".join(clock_references)
        unit = _normalize_xml_value(var.get("unit"))
        if unit and (var_type == "Real" or normalized_fmi3_type in {"Float32", "Float64"}):
            type_attrs["unit"] = unit
        display_unit = var.get("displayUnit")
        display_unit_name = _normalize_xml_value(
            display_unit.get("name") if isinstance(display_unit, dict) else display_unit
        )
        if display_unit_name and "unit" in type_attrs:
            type_attrs["displayUnit"] = display_unit_name
        quantity = _normalize_xml_value(var.get("quantity"))
        numeric_fmi3_type = normalized_fmi3_type in {
            "Float32", "Float64", "Int8", "UInt8", "Int16", "UInt16",
            "Int32", "UInt32", "Int64", "UInt64", "Enumeration",
        }
        if fmi_major_version >= 3 and numeric_fmi3_type and quantity:
            type_attrs["quantity"] = quantity
        if fmi_major_version >= 3 and numeric_fmi3_type:
            for field in ("min", "max"):
                value = var.get(field)
                if normalized_fmi3_type in {
                    "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64", "Enumeration",
                }:
                    if not isinstance(value, int) or isinstance(value, bool):
                        continue
                    type_attrs[field] = str(value)
                elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    type_attrs[field] = format(value, ".17g")
        if fmi_major_version >= 3 and normalized_fmi3_type in {"Float32", "Float64"}:
            nominal = var.get("nominal")
            if isinstance(nominal, (int, float)) and not isinstance(nominal, bool) and math.isfinite(nominal):
                type_attrs["nominal"] = format(nominal, ".17g")
            if numeric_reference in continuous_state_references and isinstance(var.get("reinit"), bool):
                type_attrs["reinit"] = str(var["reinit"]).lower()
            for field in ("relativeQuantity", "unbounded"):
                value = var.get(field)
                if isinstance(value, bool):
                    type_attrs[field] = str(value).lower()
        if fmi_major_version >= 3 and normalized_fmi3_type == "Binary":
            mime_type = _normalize_xml_value(var.get("mimeType"))
            if mime_type:
                type_attrs["mimeType"] = mime_type
            max_size = var.get("maxSize")
            if isinstance(max_size, int) and not isinstance(max_size, bool) and max_size >= 0:
                type_attrs["maxSize"] = str(max_size)
        if fmi_major_version < 3 and var_type == "Real":
            for field in ("min", "max", "nominal"):
                value = var.get(field)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    type_attrs[field] = format(value, ".17g")
            for field in ("relativeQuantity", "unbounded"):
                value = var.get(field)
                if isinstance(value, bool):
                    type_attrs[field] = str(value).lower()
        elif fmi_major_version < 3 and var_type in {"Integer", "Enumeration"}:
            quantity = _normalize_xml_value(var.get("quantity"))
            if quantity:
                type_attrs["quantity"] = quantity
            for field in ("min", "max"):
                value = var.get(field)
                if isinstance(value, int) and not isinstance(value, bool):
                    type_attrs[field] = str(value)
        if fmi_major_version >= 3 and normalized_fmi3_type == "Clock":
            interval_variability = _normalize_xml_value(
                var.get("intervalVariability") or declared_type.get("intervalVariability")
            )
            if interval_variability:
                type_attrs["intervalVariability"] = interval_variability
            for field in (
                "canBeDeactivated", "priority", "intervalDecimal", "shiftDecimal", "supportsFraction",
                "resolution", "intervalCounter", "shiftCounter",
            ):
                value = var.get(field, declared_type.get(field))
                if isinstance(value, bool):
                    type_attrs[field] = str(value).lower()
                elif field in {"intervalDecimal", "shiftDecimal"}:
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                        type_attrs[field] = format(value, ".17g")
                elif isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    type_attrs[field] = str(value)
        raw_start_value = var.get("start")
        start_value = _format_fmi_start_value(raw_start_value)
        # FMI 2: start is required by spec when causality=parameter/input or initial=exact/approx.
        # Provide a safe default if the source FMU metadata omitted it.
        if fmi_major_version < 3 and start_value is None:
            _requires_start = (
                (causality or "").lower() in {"parameter", "input"}
                or (initial or "").lower() in {"exact", "approx"}
            )
            if _requires_start:
                if var_type == "Boolean":
                    start_value = "false"
                elif var_type == "String":
                    start_value = ""
                elif var_type == "Enumeration":
                    start_value = "1"
                else:
                    start_value = "0"
        # FMI 3: Binary and String use <Start value="..."/> child elements,
        # Clock has no start at all.  Other types use a start attribute.
        _fmi3_start_child_types = {"Binary", "String"}
        if start_value is not None and (initial or "").lower() != "calculated":
            if fmi_major_version >= 3 and normalized_fmi3_type in _fmi3_start_child_types:
                pass  # handled after element creation below
            elif fmi_major_version >= 3 and normalized_fmi3_type == "Clock":
                pass  # Clock has no start in FMI 3 schema
            else:
                type_attrs["start"] = start_value
        if declared_type_name and declared_type_name in exported_declared_type_names:
            type_attrs["declaredType"] = declared_type_name

        if fmi_major_version >= 3:
            type_attrs.update(scalar_attrs)
            typed_variable = ET.SubElement(model_variables, normalized_fmi3_type, type_attrs)
            for dimension in var.get("dimensions", []) or []:
                dimension_attrs = {}
                if dimension.get("start") is not None:
                    dimension_attrs["start"] = str(dimension["start"])
                elif dimension.get("valueReference") is not None:
                    dimension_attrs["valueReference"] = str(dimension["valueReference"])
                if dimension_attrs:
                    ET.SubElement(typed_variable, "Dimension", dimension_attrs)
            # Binary/String: emit <Start value="..."/> child element(s)
            if raw_start_value is not None and (initial or "").lower() != "calculated":
                if normalized_fmi3_type == "Binary":
                    raw_values = _flatten_fmi_start_values(raw_start_value)
                    for raw_value in raw_values:
                        formatted_value = _format_fmi_start_value(raw_value) or ""
                        hex_value = _format_fmi3_binary_start_value(raw_value, formatted_value)
                        ET.SubElement(typed_variable, "Start", {"value": hex_value})
                elif normalized_fmi3_type == "String":
                    raw_values = _flatten_fmi_start_values(raw_start_value)
                    for raw_value in raw_values:
                        formatted_value = _format_fmi_start_value(raw_value) or ""
                        ET.SubElement(typed_variable, "Start", {"value": formatted_value})
            for alias in var.get("aliases", []) or []:
                if not isinstance(alias, dict):
                    continue
                alias_name = _normalize_xml_value(alias.get("name"))
                if not alias_name:
                    continue
                alias_attrs = {"name": alias_name}
                alias_description = _normalize_xml_value(alias.get("description"))
                if alias_description:
                    alias_attrs["description"] = alias_description
                if normalized_fmi3_type in {"Float32", "Float64"}:
                    alias_display_unit = _normalize_xml_value(alias.get("displayUnit"))
                    if alias_display_unit:
                        alias_attrs["displayUnit"] = alias_display_unit
                ET.SubElement(typed_variable, "Alias", alias_attrs)
        else:
            scalar = ET.SubElement(model_variables, "ScalarVariable", scalar_attrs)
            if var_type in ("Integer", "Boolean", "String", "Enumeration"):
                ET.SubElement(scalar, var_type, type_attrs)
            else:
                ET.SubElement(scalar, "Real", type_attrs)

        if (causality or "").lower() == "output":
            output_indexes.append((written_index, value_reference))
        if fmi_major_version >= 3 and _is_fmi3_initial_unknown(var, initial):
            initial_unknown_indexes.append(value_reference)
        elif fmi_major_version < 3 and _is_fmi2_initial_unknown(var, initial):
            initial_unknown_indexes.append(written_index)

    model_structure = ET.SubElement(root, "ModelStructure")
    source_model_structure = model_metadata.get("modelStructure")
    if supports_model_exchange and isinstance(source_model_structure, dict):
        model_structure_fields = (
            ("outputs", "Output"),
            ("derivatives", "ContinuousStateDerivative"),
            ("clockedStates", "ClockedState"),
            ("initialUnknowns", "InitialUnknown"),
            ("eventIndicators", "EventIndicator"),
        )

        def structure_reference(entry: dict, *, dependency_name: str | None = None) -> int | None:
            if dependency_name:
                return written_indexes_by_name.get(dependency_name)
            name = entry.get("name")
            if isinstance(name, str) and name in written_indexes_by_name:
                return written_indexes_by_name[name]
            reference = entry.get("valueReference")
            if isinstance(reference, int) and not isinstance(reference, bool):
                return written_indexes_by_reference.get(reference)
            return None

        if fmi_major_version >= 3:
            for field, element_name in model_structure_fields:
                for entry in source_model_structure.get(field, []) or []:
                    if not isinstance(entry, dict):
                        continue
                    reference = entry.get("valueReference")
                    if isinstance(reference, bool) or not isinstance(reference, int):
                        continue
                    element_attributes = {"valueReference": str(reference)}
                    dependencies = entry.get("dependencies")
                    if isinstance(dependencies, list):
                        element_attributes["dependencies"] = " ".join(str(item) for item in dependencies)
                    dependency_kinds = entry.get("dependenciesKind")
                    if isinstance(dependency_kinds, list):
                        element_attributes["dependenciesKind"] = " ".join(str(item) for item in dependency_kinds)
                    ET.SubElement(model_structure, element_name, element_attributes)
        else:
            for field, container_name in (
                ("outputs", "Outputs"),
                ("derivatives", "Derivatives"),
                ("initialUnknowns", "InitialUnknowns"),
            ):
                entries = source_model_structure.get(field, []) or []
                if not entries:
                    continue
                container = ET.SubElement(model_structure, container_name)
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    index = structure_reference(entry)
                    if index is None:
                        raise HTTPException(status_code=422, detail="FMI 2 ModelStructure references an unexported variable")
                    unknown_attributes = {"index": str(index)}
                    dependencies = entry.get("dependencies")
                    dependency_names = entry.get("dependencyNames")
                    if isinstance(dependencies, list):
                        mapped_dependencies = []
                        for dependency_index, dependency in enumerate(dependencies):
                            dependency_name = (
                                dependency_names[dependency_index]
                                if isinstance(dependency_names, list) and dependency_index < len(dependency_names)
                                else None
                            )
                            mapped = structure_reference({"valueReference": dependency}, dependency_name=dependency_name)
                            if mapped is None:
                                raise HTTPException(status_code=422, detail="FMI 2 ModelStructure dependency is not exported")
                            mapped_dependencies.append(str(mapped))
                        unknown_attributes["dependencies"] = " ".join(mapped_dependencies)
                    ET.SubElement(container, "Unknown", unknown_attributes)
    else:
        if fmi_major_version >= 3:
            for _, value_reference in output_indexes:
                ET.SubElement(model_structure, "Output", {"valueReference": str(value_reference)})
            for value_reference in initial_unknown_indexes:
                ET.SubElement(model_structure, "InitialUnknown", {"valueReference": str(value_reference)})
        elif output_indexes:
            outputs = ET.SubElement(model_structure, "Outputs")
            for idx, _ in output_indexes:
                ET.SubElement(outputs, "Unknown", {"index": str(idx)})
        if fmi_major_version < 3 and initial_unknown_indexes:
            initial_unknowns = ET.SubElement(model_structure, "InitialUnknowns")
            for idx in initial_unknown_indexes:
                ET.SubElement(initial_unknowns, "Unknown", {"index": str(idx)})

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes


def _is_fmi3_initial_unknown(variable: dict, initial: Any) -> bool:
    """Return whether FMI 3 requires this proxy variable in InitialUnknown."""
    causality = str(variable.get("causality") or "local").lower()
    if causality == "calculatedparameter":
        return True

    if initial is not None:
        is_unknown = str(initial).lower() in {"approx", "calculated"}
        if causality == "output":
            return is_unknown
        # Clocked variables may be included when the FMU chooses to initialize
        # them in Initialization Mode; an explicit unknown initial value is
        # the metadata signal that this proxy preserves that choice.
        return is_unknown and bool(variable.get("clocks"))

    variability = str(variable.get("variability") or "").lower()
    variable_type = _normalize_proxy_fmi3_type(variable.get("type"))
    if not variability:
        if causality in {"input", "output", "local"}:
            variability = "continuous" if variable_type in {"Float32", "Float64"} else "discrete"
        elif causality == "independent":
            variability = "continuous"
        else:
            variability = "fixed"

    # FMI 3 requires non-clocked discrete and continuous outputs in this list;
    # constant outputs default to exact and are not initialization unknowns.
    return (
        causality == "output"
        and variable_type != "Clock"
        and not variable.get("clocks")
        and variability in {"discrete", "continuous"}
    )


def _is_fmi2_initial_unknown(variable: dict, initial: Any) -> bool:
    """Return whether FMI 2 requires this proxy variable in InitialUnknowns."""
    causality = str(variable.get("causality") or "local").lower()
    if causality == "calculatedparameter":
        return True
    if causality != "output":
        return False

    if initial is not None:
        return str(initial).lower() in {"approx", "calculated"}

    variable_type = str(variable.get("type") or "Real").lower()
    variability = str(variable.get("variability") or "").lower()
    if not variability:
        variability = "continuous" if variable_type == "real" else "discrete"
    # FMI 2 defaults output initial to "exact" for constant outputs and to
    # "calculated" for discrete/continuous outputs.
    return variability in {"discrete", "continuous"}


def _collect_runtime_files(
    *,
    runtime_path: str | Path,
    fmi_version: str,
    model_identifier: str,
) -> list[tuple[Path, str]]:
    runtime_root = Path(runtime_path).resolve()
    binaries_root = (runtime_root / "binaries").resolve()
    if not binaries_root.exists() or not binaries_root.is_dir():
        raise HTTPException(
            status_code=503,
            detail="FMU proxy runtime binaries are not provisioned on Lab Gateway",
        )
    files: list[tuple[Path, str]] = []
    fmi_major_version = _parse_fmi_major_version(fmi_version)
    fmi3_platform_map = {
        "win64": ("x86_64-windows", ".dll"),
        "linux64": ("x86_64-linux", ".so"),
        "darwin64": ("x86_64-darwin", ".dylib"),
    }
    for file_path in binaries_root.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith("."):
            rel_path = file_path.relative_to(binaries_root)
            if fmi_major_version >= 3:
                parts = rel_path.parts
                if not parts:
                    continue
                platform = fmi3_platform_map.get(parts[0])
                if platform is None:
                    continue
                platform_dir, expected_suffix = platform
                archive_name = f"binaries/{platform_dir}/{model_identifier}{expected_suffix}"
            else:
                archive_name = file_path.relative_to(runtime_root).as_posix()
            files.append((file_path, archive_name))
    if not files:
        raise HTTPException(
            status_code=503,
            detail="FMU proxy runtime binaries are not provisioned on Lab Gateway",
        )
    return files
