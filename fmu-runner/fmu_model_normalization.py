from __future__ import annotations

import math
import re
from typing import Any, Optional

from fastapi import HTTPException
from fmi_ls_struct import normalize_fmi_ls_struct


ModelMetadata = dict[str, Any]


def _normalize_fmi_number(value: Any, *, integer: bool = False) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if integer:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
            try:
                return int(value.strip())
            except (ValueError, OverflowError):
                return None
        if isinstance(value, float) and math.isfinite(value) and value.is_integer():
            return int(value)
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _normalize_fmi_non_negative_integer(value: Any) -> int | None:
    number = _normalize_fmi_number(value, integer=True)
    return number if isinstance(number, int) and number >= 0 else None


def normalize_variable(raw: dict[str, Any], fallback_reference: int) -> dict[str, Any]:
    value_reference = raw.get("valueReference")
    if value_reference is None:
        value_reference = fallback_reference
    entry: dict[str, Any] = {
        "name": str(raw.get("name") or ""),
        "type": str(raw.get("type") or "Real"),
        "causality": str(raw.get("causality") or "local"),
        "variability": str(raw.get("variability") or "continuous"),
        "valueReference": int(value_reference),
    }
    interval_variability = raw.get("intervalVariability")
    if entry["type"] == "Clock" and interval_variability in {
        "constant", "fixed", "tunable", "changing", "countdown", "triggered",
    }:
        entry["intervalVariability"] = interval_variability
    if entry["type"] == "Clock":
        for attribute in ("canBeDeactivated", "supportsFraction"):
            value = raw.get(attribute)
            if isinstance(value, bool):
                entry[attribute] = value
        for attribute in ("intervalDecimal", "shiftDecimal"):
            value = raw.get(attribute)
            if value is None or isinstance(value, bool):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(number):
                entry[attribute] = number
        for attribute in ("priority", "resolution", "intervalCounter", "shiftCounter"):
            value = _normalize_fmi_non_negative_integer(raw.get(attribute))
            if value is not None:
                entry[attribute] = value
    alias = raw.get("alias")
    if alias in {"noAlias", "alias", "negatedAlias"}:
        entry["alias"] = alias
    alias_of = raw.get("aliasOf")
    if isinstance(alias_of, str) and alias_of.strip():
        entry["aliasOf"] = alias_of.strip()[:512]
    raw_aliases = raw.get("aliases")
    if isinstance(raw_aliases, list) and len(raw_aliases) <= 256:
        aliases = []
        for raw_alias in raw_aliases:
            if not isinstance(raw_alias, dict):
                continue
            name = raw_alias.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            alias_entry = {"name": name.strip()[:512]}
            for field, maximum_length in (("description", 4096), ("displayUnit", 256)):
                value = raw_alias.get(field)
                if isinstance(value, str) and value.strip():
                    alias_entry[field] = value.strip()[:maximum_length]
            aliases.append(alias_entry)
        if aliases:
            entry["aliases"] = aliases
    mime_type = raw.get("mimeType")
    if isinstance(mime_type, str) and mime_type.strip():
        entry["mimeType"] = mime_type.strip()[:256]
    max_size = raw.get("maxSize")
    normalized_max_size = _normalize_fmi_non_negative_integer(max_size)
    if normalized_max_size is not None:
        entry["maxSize"] = normalized_max_size
    for attribute in ("relativeQuantity", "unbounded"):
        value = raw.get(attribute)
        if isinstance(value, bool):
            entry[attribute] = value
    if raw.get("unit") is not None:
        entry["unit"] = raw.get("unit")
    if raw.get("start") is not None:
        entry["start"] = raw.get("start")
    initial = raw.get("initial")
    if isinstance(initial, str) and initial.strip():
        entry["initial"] = initial.strip()[:32]
    raw_clocks = raw.get("clocks")
    if isinstance(raw_clocks, list) and len(raw_clocks) <= 256:
        clock_references = [
            reference
            for item in raw_clocks
            if (reference := _normalize_fmi_non_negative_integer(item)) is not None
        ]
        if clock_references:
            entry["clocks"] = clock_references
    nominal = raw.get("nominal")
    if nominal is not None and not isinstance(nominal, bool):
        try:
            normalized_nominal = float(nominal)
        except (TypeError, ValueError, OverflowError):
            normalized_nominal = 0.0
        if math.isfinite(normalized_nominal) and normalized_nominal > 0:
            entry["nominal"] = normalized_nominal
    integer_type = entry["type"] in {
        "Integer", "Enumeration", "Int8", "UInt8", "Int16", "UInt16",
        "Int32", "UInt32", "Int64", "UInt64",
    }
    for bound in ("min", "max"):
        raw_bound = raw.get(bound)
        if raw_bound is None:
            continue
        value = _normalize_fmi_number(raw_bound, integer=integer_type)
        if value is not None:
            entry[bound] = value
    description = raw.get("description")
    if isinstance(description, str) and description.strip():
        entry["description"] = description.strip()[:4096]
    display_name = raw.get("displayName")
    if isinstance(display_name, str) and display_name.strip():
        entry["displayName"] = display_name.strip()[:256]
    quantity = raw.get("quantity")
    if isinstance(quantity, str) and quantity.strip():
        entry["quantity"] = quantity.strip()[:256]
    display_unit = raw.get("displayUnit")
    if isinstance(display_unit, str) and display_unit.strip():
        entry["displayUnit"] = display_unit.strip()[:64]
    elif isinstance(display_unit, dict):
        name = display_unit.get("name")
        try:
            factor = float(display_unit.get("factor", 1.0))
            offset = float(display_unit.get("offset", 0.0))
        except (TypeError, ValueError, OverflowError):
            factor = 0.0
            offset = 0.0
        raw_inverse = display_unit.get("inverse", False)
        inverse = raw_inverse is True or str(raw_inverse).strip().lower() in {"true", "1"}
        if (
            isinstance(name, str)
            and name.strip()
            and math.isfinite(factor)
            and factor != 0
            and math.isfinite(offset)
            and (not inverse or offset == 0)
        ):
            normalized_display_unit: dict[str, Any] = {
                "name": name.strip()[:64],
                "factor": factor,
                "offset": offset,
            }
            if inverse:
                normalized_display_unit["inverse"] = True
            entry["displayUnit"] = normalized_display_unit
    raw_dimensions = raw.get("dimensions")
    if isinstance(raw_dimensions, list) and len(raw_dimensions) <= 64:
        dimensions = []
        for dimension in raw_dimensions:
            if not isinstance(dimension, dict):
                continue
            normalized_dimension = {}
            for field in ("start", "valueReference"):
                value = dimension.get(field)
                normalized_value = _normalize_fmi_non_negative_integer(value)
                if normalized_value is not None:
                    normalized_dimension[field] = normalized_value
            variable_name = dimension.get("variableName")
            if isinstance(variable_name, str) and variable_name.strip():
                normalized_dimension["variableName"] = variable_name.strip()[:256]
            if normalized_dimension:
                dimensions.append(normalized_dimension)
        if dimensions:
            entry["dimensions"] = dimensions
    raw_declared_type = raw.get("declaredType")
    if isinstance(raw_declared_type, dict):
        declared_type = {}
        for field, maximum_length in (
            ("name", 256), ("type", 64), ("description", 4096),
            ("unit", 128), ("quantity", 256), ("displayUnit", 64), ("mimeType", 256),
            ("intervalVariability", 32),
        ):
            value = raw_declared_type.get(field)
            if isinstance(value, str) and value.strip():
                declared_type[field] = value.strip()[:maximum_length]
        for bound in ("min", "max"):
            value = raw_declared_type.get(bound)
            number = _normalize_fmi_number(value, integer=integer_type)
            if number is not None:
                declared_type[bound] = number
        nominal = raw_declared_type.get("nominal")
        if nominal is not None and not isinstance(nominal, bool):
            try:
                normalized_nominal = float(nominal)
            except (TypeError, ValueError, OverflowError):
                normalized_nominal = 0.0
            if math.isfinite(normalized_nominal) and normalized_nominal > 0:
                declared_type["nominal"] = normalized_nominal
        declared_max_size = _normalize_fmi_non_negative_integer(raw_declared_type.get("maxSize"))
        if declared_max_size is not None:
            declared_type["maxSize"] = declared_max_size
        for attribute in ("relativeQuantity", "unbounded"):
            value = raw_declared_type.get(attribute)
            if isinstance(value, bool):
                declared_type[attribute] = value
        for attribute in ("supportsFraction", "canBeDeactivated"):
            value = raw_declared_type.get(attribute)
            if isinstance(value, bool):
                declared_type[attribute] = value
        for attribute in ("intervalDecimal", "shiftDecimal"):
            value = raw_declared_type.get(attribute)
            if value is None or isinstance(value, bool):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(number):
                declared_type[attribute] = number
        for attribute in ("resolution", "intervalCounter", "shiftCounter", "priority"):
            value = _normalize_fmi_non_negative_integer(raw_declared_type.get(attribute))
            if value is not None:
                declared_type[attribute] = value
        raw_items = raw_declared_type.get("items")
        if isinstance(raw_items, list) and len(raw_items) <= 256:
            items = []
            for item in raw_items:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                    continue
                integer_value = _normalize_fmi_number(item.get("value"), integer=True)
                if not isinstance(integer_value, int):
                    continue
                item_value: int | str = integer_value if abs(integer_value) <= (2**53 - 1) else str(integer_value)
                normalized_item = {"name": item["name"].strip()[:256], "value": item_value}
                description = item.get("description")
                if isinstance(description, str) and description.strip():
                    normalized_item["description"] = description.strip()[:1024]
                if normalized_item["name"]:
                    items.append(normalized_item)
            if items:
                declared_type["items"] = items
        if declared_type:
            entry["declaredType"] = declared_type
    enum_items = raw.get("enumItems")
    if entry["type"] == "Enumeration" and isinstance(enum_items, list) and len(enum_items) <= 256:
        normalized_items = []
        for item in enum_items:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            integer_value = _normalize_fmi_number(item.get("value"), integer=True)
            if not isinstance(integer_value, int):
                continue
            enum_value: int | str = integer_value if abs(integer_value) <= (2**53 - 1) else str(integer_value)
            normalized_item = {"value": enum_value, "name": item["name"].strip()[:256]}
            item_description = item.get("description")
            if isinstance(item_description, str) and item_description.strip():
                normalized_item["description"] = item_description.strip()[:1024]
            if normalized_item["name"]:
                normalized_items.append(normalized_item)
        if normalized_items:
            entry["enumItems"] = normalized_items
    return entry


def normalize_model_metadata(payload: dict[str, Any]) -> ModelMetadata:
    raw_variables = payload.get("modelVariables")
    if raw_variables is None:
        raw_variables = payload.get("variables")
    if not isinstance(raw_variables, list):
        raise HTTPException(status_code=502, detail="Station backend response is missing model variables")

    supports_cs = payload.get("supportsCoSimulation")
    supports_me = payload.get("supportsModelExchange")
    simulation_kind = payload.get("simulationKind")
    simulation_type = payload.get("simulationType")

    if simulation_kind is None:
        if simulation_type == "CoSimulation":
            simulation_kind = "coSimulation"
        elif simulation_type == "ModelExchange":
            simulation_kind = "modelExchange"
        else:
            simulation_kind = "coSimulation" if supports_cs else ("modelExchange" if supports_me else "unknown")

    if simulation_type is None:
        simulation_type = "CoSimulation" if simulation_kind == "coSimulation" else (
            "ModelExchange" if simulation_kind == "modelExchange" else "Unknown"
        )

    raw_execution_interface = payload.get("executionInterface")
    if isinstance(raw_execution_interface, str) and raw_execution_interface in {"CoSimulation", "ModelExchange"}:
        execution_interface = raw_execution_interface
    elif simulation_type in {"CoSimulation", "ModelExchange"}:
        execution_interface = simulation_type
    else:
        execution_interface = None
    raw_supports_execution = payload.get("supportsExecution")
    supports_execution = (
        raw_supports_execution
        if isinstance(raw_supports_execution, bool)
        else execution_interface is not None
    )

    def optional_number(name: str) -> Optional[float]:
        value = payload.get(name)
        return float(value) if value is not None else None

    normalized = {
        "modelName": str(payload.get("modelName") or "DecentraLabsProxy"),
        "guid": payload.get("guid"),
        "fmiVersion": str(payload.get("fmiVersion") or "2.0"),
        "simulationKind": str(simulation_kind),
        "simulationType": str(simulation_type),
        "executionInterface": execution_interface,
        "supportsExecution": supports_execution,
        "supportsCoSimulation": bool(supports_cs if supports_cs is not None else simulation_kind == "coSimulation"),
        "supportsModelExchange": bool(supports_me if supports_me is not None else simulation_kind == "modelExchange"),
        "supportsFmiLsDae": payload.get("supportsFmiLsDae") is True,
        "defaultStartTime": optional_number("defaultStartTime"),
        "defaultStopTime": optional_number("defaultStopTime"),
        "defaultStepSize": optional_number("defaultStepSize"),
        "modelVariables": [],
    }
    fmi_ls_dae = payload.get("fmiLsDae")
    if normalized["supportsFmiLsDae"]:
        # Keep only bounded summary metadata and the selector name required to
        # enforce its FMI write phases. The full manifest remains private.
        if fmi_ls_dae is None:
            raise HTTPException(status_code=502, detail="Station backend omitted FMI-LS-DAE selector metadata")
        if fmi_ls_dae is not None:
            if not isinstance(fmi_ls_dae, dict):
                raise HTTPException(status_code=502, detail="Station backend returned invalid FMI-LS-DAE metadata")
            enable_dae_parameter = fmi_ls_dae.get("enableDAEParameter")
            algebraic_variables = fmi_ls_dae.get("algebraicVariables")
            residual_variable_count = fmi_ls_dae.get("residualVariableCount")
            enable_variable = next(
                (
                    variable for variable in raw_variables
                    if isinstance(variable, dict)
                    and variable.get("name") == enable_dae_parameter
                    and variable.get("causality") == "structuralParameter"
                    and variable.get("type") == "Boolean"
                    and variable.get("variability") in ("fixed", "tunable")
                ),
                None,
            )
            if (
                fmi_ls_dae.get("manifestName") != "org.fmi-standard.fmi-ls-dae"
                or fmi_ls_dae.get("manifestVersion") != "1.0.0-alpha.1"
                or not isinstance(enable_dae_parameter, str)
                or not enable_dae_parameter
                or enable_variable is None
                or not isinstance(algebraic_variables, list)
                or len(algebraic_variables) > 100_000
                or any(not isinstance(name, str) or not name or len(name) > 1024 for name in algebraic_variables)
                or len(set(algebraic_variables)) != len(algebraic_variables)
                or isinstance(residual_variable_count, bool)
                or not isinstance(residual_variable_count, int)
                or residual_variable_count < 0
                or residual_variable_count > 100_000
            ):
                raise HTTPException(status_code=502, detail="Station backend returned invalid FMI-LS-DAE metadata")
            normalized["fmiLsDae"] = {
                "manifestName": "org.fmi-standard.fmi-ls-dae",
                "manifestVersion": "1.0.0-alpha.1",
                "enableDAEParameter": enable_dae_parameter,
                "algebraicVariables": algebraic_variables,
                "residualVariableCount": residual_variable_count,
            }
    elif payload.get("fmiLsDae") is not None:
        raise HTTPException(status_code=502, detail="Station backend returned inconsistent FMI-LS-DAE metadata")
    for field in ("numberOfContinuousStates", "numberOfEventIndicators"):
        value = payload.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            normalized[field] = value

    for field, maximum_length in (
        ("description", 4096),
        ("author", 256),
        ("version", 128),
        ("copyright", 1024),
        ("license", 256),
        ("generationTool", 256),
        ("generationDateAndTime", 64),
    ):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            normalized[field] = value.strip()[:maximum_length]
    variable_naming_convention = payload.get("variableNamingConvention")
    if variable_naming_convention in {"flat", "structured"}:
        normalized["variableNamingConvention"] = variable_naming_convention
    default_tolerance = payload.get("defaultTolerance")
    if default_tolerance is not None and not isinstance(default_tolerance, bool):
        try:
            tolerance_value = float(default_tolerance)
        except (TypeError, ValueError, OverflowError):
            tolerance_value = 0.0
        if math.isfinite(tolerance_value) and tolerance_value > 0:
            normalized["defaultTolerance"] = tolerance_value
    raw_capabilities = payload.get("capabilities")
    if isinstance(raw_capabilities, dict):
        capabilities = {}
        for field in (
            "needsExecutionTool",
            "canBeInstantiatedOnlyOncePerProcess",
            "canNotUseMemoryManagementFunctions",
            "canGetAndSetFMUstate",
            "canSerializeFMUstate",
            "canHandleVariableCommunicationStepSize",
            "canInterpolateInputs",
            "canRunAsynchronuously",
            "providesDirectionalDerivative",
            "providesAdjointDerivatives",
            "providesPerElementDependencies",
            "hasEventMode",
            "providesIntermediateUpdate",
            "canReturnEarlyAfterIntermediateUpdate",
            "providesEvaluateDiscreteStates",
            "needsCompletedIntegratorStep",
        ):
            value = raw_capabilities.get(field)
            if isinstance(value, bool):
                capabilities[field] = value
        for field in ("maxOutputDerivativeOrder", "recommendedIntermediateInputSmoothness"):
            value = raw_capabilities.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                capabilities[field] = value
        fixed_step = raw_capabilities.get("fixedInternalStepSize")
        if fixed_step is not None and not isinstance(fixed_step, bool):
            try:
                fixed_step_value = float(fixed_step)
            except (TypeError, ValueError, OverflowError):
                fixed_step_value = 0.0
            if math.isfinite(fixed_step_value) and fixed_step_value > 0:
                capabilities["fixedInternalStepSize"] = fixed_step_value
        if capabilities:
            normalized["capabilities"] = capabilities

    guid = payload.get("guid")
    if guid:
        normalized["guid"] = str(guid)

    for index, variable in enumerate(raw_variables, start=1):
        if not isinstance(variable, dict):
            raise HTTPException(status_code=502, detail="Station backend returned an invalid model variable entry")
        normalized["modelVariables"].append(normalize_variable(variable, index))

    raw_unit_definitions = payload.get("unitDefinitions")
    if isinstance(raw_unit_definitions, list) and len(raw_unit_definitions) <= 1024:
        unit_definitions = []
        base_unit_fields = ("kg", "m", "s", "A", "K", "mol", "cd", "rad")
        for raw_unit in raw_unit_definitions:
            if not isinstance(raw_unit, dict):
                continue
            name = raw_unit.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            unit_entry: dict[str, Any] = {"name": name.strip()[:256]}
            raw_base_unit = raw_unit.get("baseUnit")
            if isinstance(raw_base_unit, dict):
                base_unit: dict[str, Any] = {}
                for field in base_unit_fields:
                    value = raw_base_unit.get(field)
                    if isinstance(value, int) and not isinstance(value, bool):
                        base_unit[field] = value
                for field, default in (("factor", 1.0), ("offset", 0.0)):
                    value = raw_base_unit.get(field)
                    if value is None:
                        continue
                    try:
                        number = float(value)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if math.isfinite(number) and (field != "factor" or number != 0) and number != default:
                        base_unit[field] = number
                # An empty BaseUnit is meaningful for dimensionless units.
                unit_entry["baseUnit"] = base_unit
            raw_display_units = raw_unit.get("displayUnits")
            if isinstance(raw_display_units, list) and len(raw_display_units) <= 256:
                display_units = []
                for raw_display_unit in raw_display_units:
                    if not isinstance(raw_display_unit, dict):
                        continue
                    display_name = raw_display_unit.get("name")
                    if not isinstance(display_name, str) or not display_name.strip():
                        continue
                    display_unit: dict[str, Any] = {"name": display_name.strip()[:256]}
                    valid = True
                    for field, default in (("factor", 1.0), ("offset", 0.0)):
                        value = raw_display_unit.get(field)
                        if value is None:
                            continue
                        try:
                            number = float(value)
                        except (TypeError, ValueError, OverflowError):
                            valid = False
                            break
                        if not math.isfinite(number) or (field == "factor" and number == 0):
                            valid = False
                            break
                        if number != default:
                            display_unit[field] = number
                    inverse = raw_display_unit.get("inverse") is True
                    if inverse and float(display_unit.get("offset", 0.0)) != 0.0:
                        valid = False
                    if not valid:
                        continue
                    if inverse:
                        display_unit["inverse"] = True
                    display_units.append(display_unit)
                if display_units:
                    unit_entry["displayUnits"] = display_units
            unit_definitions.append(unit_entry)
        if unit_definitions:
            normalized["unitDefinitions"] = unit_definitions

    raw_type_definitions = payload.get("typeDefinitions")
    if isinstance(raw_type_definitions, list) and len(raw_type_definitions) <= 1024:
        type_definitions = []
        integer_type_names = {
            "Integer", "Enumeration", "Int8", "UInt8", "Int16", "UInt16",
            "Int32", "UInt32", "Int64", "UInt64",
        }
        for raw_type in raw_type_definitions:
            if not isinstance(raw_type, dict):
                continue
            name = raw_type.get("name")
            type_name = raw_type.get("type")
            if not isinstance(name, str) or not name.strip() or not isinstance(type_name, str) or not type_name.strip():
                continue
            declared_type: dict[str, Any] = {
                "name": name.strip()[:256],
                "type": type_name.strip()[:64],
            }
            for field, maximum_length in (
                ("description", 4096), ("unit", 128), ("quantity", 256),
                ("displayUnit", 256), ("mimeType", 256), ("intervalVariability", 32),
            ):
                value = raw_type.get(field)
                if isinstance(value, str) and value.strip():
                    declared_type[field] = value.strip()[:maximum_length]
            for field in ("min", "max", "nominal", "intervalDecimal", "shiftDecimal"):
                value = raw_type.get(field)
                number = _normalize_fmi_number(
                    value,
                    integer=field in {"min", "max"} and type_name.strip() in integer_type_names,
                )
                if number is not None:
                    declared_type[field] = number
            for field in ("relativeQuantity", "unbounded", "supportsFraction", "canBeDeactivated"):
                value = raw_type.get(field)
                if isinstance(value, bool):
                    declared_type[field] = value
            for field in ("resolution", "intervalCounter", "shiftCounter", "priority"):
                value = _normalize_fmi_non_negative_integer(raw_type.get(field))
                if value is not None:
                    declared_type[field] = value
            max_size = _normalize_fmi_non_negative_integer(raw_type.get("maxSize"))
            if max_size is not None:
                declared_type["maxSize"] = max_size
            raw_items = raw_type.get("items")
            if isinstance(raw_items, list) and len(raw_items) <= 256:
                items = []
                for raw_item in raw_items:
                    if not isinstance(raw_item, dict):
                        continue
                    item_name = raw_item.get("name")
                    item_value = raw_item.get("value")
                    if not isinstance(item_name, str) or not item_name.strip() or isinstance(item_value, bool):
                        continue
                    try:
                        if isinstance(item_value, int):
                            integer_value = item_value
                        elif isinstance(item_value, float) and math.isfinite(item_value) and item_value.is_integer():
                            integer_value = int(item_value)
                        elif isinstance(item_value, str) and re.fullmatch(r"[+-]?\d+", item_value.strip()):
                            integer_value = int(item_value.strip())
                        else:
                            continue
                    except (TypeError, ValueError, OverflowError):
                        continue
                    item = {"name": item_name.strip()[:256], "value": str(integer_value)}
                    description = raw_item.get("description")
                    if isinstance(description, str) and description.strip():
                        item["description"] = description.strip()[:1024]
                    items.append(item)
                if items:
                    declared_type["items"] = items
            type_definitions.append(declared_type)
        if type_definitions:
            normalized["typeDefinitions"] = type_definitions

    fmi_ls_struct = None
    if normalized["fmiVersion"].split(".", 1)[0] == "3":
        fmi_ls_struct = normalize_fmi_ls_struct(
            payload.get("fmiLsStruct"),
            variable_names=[variable["name"] for variable in normalized["modelVariables"]],
        )
    if fmi_ls_struct is not None:
        normalized["fmiLsStruct"] = fmi_ls_struct

    return normalized
