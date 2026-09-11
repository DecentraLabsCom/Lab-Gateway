from datetime import datetime, timezone
from pathlib import Path
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


def _proxy_model_identifier(model_metadata: dict) -> str:
    # Keep a stable identifier so the native runtime binary name stays generic.
    return "decentralabs_proxy"


def _validate_proxy_generation_supported(model_metadata: dict):
    simulation_kind = str(model_metadata.get("simulationKind") or "coSimulation").lower()
    if simulation_kind != "cosimulation":
        raise HTTPException(status_code=422, detail="Generated proxy FMUs currently support only Co-Simulation models")

    if _parse_fmi_major_version(model_metadata.get("fmiVersion")) < 3:
        return

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
    }
    for variable in model_metadata.get("modelVariables", []):
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
        for dimension in variable.get("dimensions", []) or []:
            if "start" not in dimension and "valueReference" not in dimension:
                raise HTTPException(
                    status_code=422,
                    detail=f"Generated FMI 3 proxy FMUs require dimension metadata for variable: {variable.get('name')}",
                )


def _build_proxy_model_description_xml(model_metadata: dict) -> bytes:
    _validate_proxy_generation_supported(model_metadata)

    model_name = _normalize_xml_value(model_metadata.get("modelName")) or "DecentraLabsProxy"
    guid = _normalize_xml_value(model_metadata.get("guid")) or "{" + uuid4().hex + "}"
    instantiation_token = _normalize_xml_value(model_metadata.get("instantiationToken")) or guid
    model_identifier = _proxy_model_identifier(model_metadata)
    fmi_major_version = _parse_fmi_major_version(model_metadata.get("fmiVersion"))
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
    if fmi_major_version >= 3:
        root_attributes["fmiVersion"] = "3.0"
        root_attributes["instantiationToken"] = instantiation_token
    else:
        root_attributes.update({
            "fmiVersion": "2.0",
            "guid": guid,
            "variableNamingConvention": "flat",
            "numberOfEventIndicators": "0",
        })
    root = ET.Element("fmiModelDescription", root_attributes)

    if fmi_major_version >= 3:
        ET.SubElement(
            root,
            "CoSimulation",
            {
                "modelIdentifier": model_identifier,
                "canHandleVariableCommunicationStepSize": "true",
                "canGetAndSetFMUState": "false",
                "canSerializeFMUState": "false",
            },
        )
    else:
        ET.SubElement(
            root,
            "CoSimulation",
            {
                "modelIdentifier": model_identifier,
                "canHandleVariableCommunicationStepSize": "true",
                "canInterpolateInputs": "false",
                "maxOutputDerivativeOrder": "0",
                "canRunAsynchronuously": "false",
                "canBeInstantiatedOnlyOncePerProcess": "false",
                "canNotUseMemoryManagementFunctions": "true",
                "canGetAndSetFMUstate": "false",
                "canSerializeFMUstate": "false",
                "providesDirectionalDerivative": "false",
            },
        )

    if declared_units:
        unit_definitions = ET.SubElement(root, "UnitDefinitions")
        for unit_name in sorted(declared_units):
            ET.SubElement(unit_definitions, "Unit", {"name": unit_name})

    if fmi_major_version < 3:
        declared_type_definitions = _collect_declared_type_definitions(model_metadata)
        if declared_type_definitions:
            type_definitions = ET.SubElement(root, "TypeDefinitions")
            for type_name in sorted(declared_type_definitions):
                declared_type = declared_type_definitions[type_name]
                simple_type_attrs = {"name": type_name}
                description = _normalize_xml_value(declared_type.get("description"))
                if description:
                    simple_type_attrs["description"] = description
                simple_type = ET.SubElement(type_definitions, "SimpleType", simple_type_attrs)
                type_tag = str(declared_type.get("type") or "Enumeration")
                typed_definition = ET.SubElement(simple_type, type_tag)
                if type_tag == "Enumeration":
                    for item in declared_type.get("items", []) or []:
                        item_attrs = {
                            "name": str(item.get("name") or ""),
                            "value": str(item.get("value") or ""),
                        }
                        item_description = _normalize_xml_value(item.get("description"))
                        if item_description:
                            item_attrs["description"] = item_description
                        ET.SubElement(typed_definition, "Item", item_attrs)

    attrs = {}
    if model_metadata.get("defaultStartTime") is not None:
        attrs["startTime"] = str(model_metadata["defaultStartTime"])
    if model_metadata.get("defaultStopTime") is not None:
        attrs["stopTime"] = str(model_metadata["defaultStopTime"])
    if model_metadata.get("defaultStepSize") is not None:
        attrs["stepSize"] = str(model_metadata["defaultStepSize"])
    if attrs:
        ET.SubElement(root, "DefaultExperiment", attrs)

    model_variables = ET.SubElement(root, "ModelVariables")
    output_indexes = []
    written_index = 0  # 1-based position in ModelVariables (independent vars excluded)

    for index, var in enumerate(model_metadata.get("modelVariables", []), start=1):
        # FMI 2: skip independent variables (time) — OpenModelica's FMI2XML parser rejects the
        # modelDescription.xml when an independent variable lacks a start attribute, even though
        # start is N.A. for that causality/variability combination per the FMI 2.0 spec.
        # FMI 3 keeps independent variables because parsers handle them correctly there.
        if fmi_major_version < 3 and (var.get("causality") or "").lower() == "independent":
            continue
        written_index += 1
        var_type = str(var.get("type", "Real") or "Real")
        value_reference = var.get("valueReference")
        if value_reference is None:
            value_reference = index
        scalar_attrs = {
            "name": str(var.get("name") or f"var_{index}"),
            "valueReference": str(value_reference),
        }
        causality = _normalize_xml_value(var.get("causality"))
        variability = _normalize_xml_value(var.get("variability"))
        initial = _normalize_xml_value(var.get("initial"))
        if causality:
            scalar_attrs["causality"] = causality
        if variability:
            scalar_attrs["variability"] = variability
        if initial:
            scalar_attrs["initial"] = initial

        type_attrs = {}
        unit = _normalize_xml_value(var.get("unit"))
        normalized_fmi3_type = _normalize_proxy_fmi3_type(var_type)
        if unit and (var_type == "Real" or normalized_fmi3_type in {"Float32", "Float64"}):
            type_attrs["unit"] = unit
        start_value = _format_fmi_start_value(var.get("start"))
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
        declared_type_name = _normalize_xml_value((var.get("declaredType") or {}).get("name"))
        if declared_type_name and fmi_major_version < 3:
            type_attrs["declaredType"] = declared_type_name

        if fmi_major_version >= 3:
            type_attrs.update(scalar_attrs)
            typed_variable = ET.SubElement(model_variables, normalized_fmi3_type, type_attrs)
            # Binary/String: emit <Start value="..."/> child element(s)
            if start_value is not None and (initial or "").lower() != "calculated":
                if normalized_fmi3_type == "Binary":
                    raw = var.get("start")
                    hex_value = _format_fmi3_binary_start_value(raw, start_value)
                    ET.SubElement(typed_variable, "Start", {"value": hex_value})
                elif normalized_fmi3_type == "String":
                    ET.SubElement(typed_variable, "Start", {"value": start_value})
            for dimension in var.get("dimensions", []) or []:
                dimension_attrs = {}
                if dimension.get("start") is not None:
                    dimension_attrs["start"] = str(dimension["start"])
                elif dimension.get("valueReference") is not None:
                    dimension_attrs["valueReference"] = str(dimension["valueReference"])
                if dimension_attrs:
                    ET.SubElement(typed_variable, "Dimension", dimension_attrs)
        else:
            scalar = ET.SubElement(model_variables, "ScalarVariable", scalar_attrs)
            if var_type in ("Integer", "Boolean", "String", "Enumeration"):
                ET.SubElement(scalar, var_type, type_attrs)
            else:
                ET.SubElement(scalar, "Real", type_attrs)

        if (causality or "").lower() == "output":
            output_indexes.append((written_index, value_reference))

    model_structure = ET.SubElement(root, "ModelStructure")
    if output_indexes:
        if fmi_major_version >= 3:
            for _, value_reference in output_indexes:
                ET.SubElement(model_structure, "Output", {"valueReference": str(value_reference)})
        else:
            outputs = ET.SubElement(model_structure, "Outputs")
            for idx, _ in output_indexes:
                ET.SubElement(outputs, "Unknown", {"index": str(idx)})

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes


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