from __future__ import annotations

import math
from typing import Any, Optional

from fastapi import HTTPException
from fmi_ls_struct import normalize_fmi_ls_struct


ModelMetadata = dict[str, Any]


def normalize_variable(raw: dict[str, Any], fallback_reference: int) -> dict[str, Any]:
    value_reference = raw.get("valueReference")
    if value_reference is None:
        value_reference = fallback_reference
    entry = {
        "name": str(raw.get("name") or ""),
        "type": str(raw.get("type") or "Real"),
        "causality": str(raw.get("causality") or "local"),
        "variability": str(raw.get("variability") or "continuous"),
        "valueReference": int(value_reference),
    }
    if raw.get("unit") is not None:
        entry["unit"] = raw.get("unit")
    if raw.get("start") is not None:
        entry["start"] = raw.get("start")
    initial = raw.get("initial")
    if isinstance(initial, str) and initial.strip():
        entry["initial"] = initial.strip()[:32]
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
        try:
            value = float(raw_bound)
            if not math.isfinite(value) or (integer_type and not value.is_integer()):
                continue
            entry[bound] = int(value) if integer_type else value
        except (TypeError, ValueError, OverflowError):
            continue
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
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    normalized_dimension[field] = value
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
            ("unit", 128), ("quantity", 256), ("displayUnit", 64),
        ):
            value = raw_declared_type.get(field)
            if isinstance(value, str) and value.strip():
                declared_type[field] = value.strip()[:maximum_length]
        for bound in ("min", "max"):
            value = raw_declared_type.get(bound)
            if value is None or isinstance(value, bool):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(number):
                declared_type[bound] = int(number) if integer_type and number.is_integer() else number
        raw_items = raw_declared_type.get("items")
        if isinstance(raw_items, list) and len(raw_items) <= 256:
            items = []
            for item in raw_items:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                    continue
                raw_value = item.get("value")
                if raw_value is None or isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
                    continue
                try:
                    number = float(raw_value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if not math.isfinite(number) or not number.is_integer():
                    continue
                normalized_item = {"name": item["name"].strip()[:256], "value": int(number)}
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
            raw_value = item.get("value")
            if raw_value is None or isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
                continue
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(numeric_value) or not numeric_value.is_integer():
                continue
            value = int(numeric_value)
            normalized_item = {"value": value, "name": item["name"].strip()[:256]}
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

    def optional_number(name: str) -> Optional[float]:
        value = payload.get(name)
        return float(value) if value is not None else None

    normalized = {
        "modelName": str(payload.get("modelName") or "DecentraLabsProxy"),
        "guid": payload.get("guid"),
        "fmiVersion": str(payload.get("fmiVersion") or "2.0"),
        "simulationKind": str(simulation_kind),
        "simulationType": str(simulation_type),
        "supportsCoSimulation": bool(supports_cs if supports_cs is not None else simulation_kind == "coSimulation"),
        "supportsModelExchange": bool(supports_me if supports_me is not None else simulation_kind == "modelExchange"),
        "defaultStartTime": optional_number("defaultStartTime"),
        "defaultStopTime": optional_number("defaultStopTime"),
        "defaultStepSize": optional_number("defaultStepSize"),
        "modelVariables": [],
    }

    for field, maximum_length in (
        ("description", 4096),
        ("author", 256),
        ("version", 128),
        ("license", 256),
        ("generationTool", 256),
    ):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            normalized[field] = value.strip()[:maximum_length]
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
            "canGetAndSetFMUstate",
            "canSerializeFMUstate",
            "canHandleVariableCommunicationStepSize",
            "providesDirectionalDerivative",
            "providesAdjointDerivatives",
        ):
            value = raw_capabilities.get(field)
            if isinstance(value, bool):
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

    fmi_ls_struct = None
    if normalized["fmiVersion"].split(".", 1)[0] == "3":
        fmi_ls_struct = normalize_fmi_ls_struct(
            payload.get("fmiLsStruct"),
            variable_names=[variable["name"] for variable in normalized["modelVariables"]],
        )
    if fmi_ls_struct is not None:
        normalized["fmiLsStruct"] = fmi_ls_struct

    return normalized
