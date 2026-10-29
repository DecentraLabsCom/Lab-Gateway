"""Build AAS shells and submodels from FMU metadata."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import urlsplit

from simulation_access_policy import build_part4_access_rules, fmi_interface_digest

FMU_DATA_PATH = os.getenv("FMU_DATA_PATH", "/app/fmu-data")


_AAS_LAB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")

_SEMANTIC_ID_SIMULATION_MODELS = "https://admin-shell.io/idta/SubmodelTemplate/SimulationModels/1/1"

_SEMANTIC_ID_SIMULATION_MODEL = "https://admin-shell.io/idta/SimulationModels/SimulationModel/1/1"

_SEMANTIC_ID_TECHNICAL_DATA = "0173-1#01-AHX837#002"

_SEMANTIC_ID_CAPABILITY_DESCRIPTION = "https://admin-shell.io/idta/SubmodelTemplate/CapabilityDescription/1/0"

_SEMANTIC_ID_ASSET_INTERFACES = "https://admin-shell.io/idta/AssetInterfacesDescription/1/1/Submodel"

_SEMANTIC_ID_CONTACT_INFORMATION = "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations"

_SEMANTIC_ID_HANDOVER_DOCUMENTATION = "0173-1#01-AHF578#003"

_SEMANTIC_ID_ARBITRARY = "https://admin-shell.io/SMT/General/Arbitrary"

_SEMANTIC_ID_SIMULATION_ACCESS_CONTROL = "urn:decentralabs:aas:SimulationAccessControl:1"

_SEMANTIC_ID_FMI_LS_RELATED_RESOURCES = "urn:decentralabs:aas:FmiLsRelatedResources:1"

_SEMANTIC_ID_ACCESS_INTERFACE_DIGEST = "urn:decentralabs:aas:SimulationAccessControl:InterfaceDigest:1"

_SEMANTIC_ID_ACCESS_GENERATED_DIGEST = "urn:decentralabs:aas:SimulationAccessControl:GeneratedPolicyDigest:1"

_SIMULATION_SEMANTICS = {
    "summary": "https://admin-shell.io/idta/SimulationModels/Summary/1/0",
    "type_of_model": "https://admin-shell.io/idta/SimulationModels/TypeOfModel/1/0",
    "license_model": "https://admin-shell.io/idta/SimulationModels/LicenseModel/1/0",
    "default_sim_time": "https://admin-shell.io/idta/SimulationModels/DefaultSimTime/1/0",
    "environment": "https://admin-shell.io/idta/SimulationModels/Environment/1/0",
    "simulation_tool": "https://admin-shell.io/idta/SimulationModels/SimulationTool/1/0",
    "sim_tool_name": "https://admin-shell.io/idta/SimulationModels/SimToolName/1/0",
    "solver": "https://admin-shell.io/idta/SimulationModels/SolverAndTolerances/1/0",
    "fixed_step_size": "https://admin-shell.io/idta/SimulationModels/FixedStepSize/1/0",
    "tolerance": "https://admin-shell.io/idta/SimulationModels/Tolerance/1/0",
    "model_file": "https://admin-shell.io/idta/SimulationModels/ModelFile/1/0",
    "model_file_type": "https://admin-shell.io/idta/SimulationModels/ModelFileType/1/0",
    "model_file_version": "https://admin-shell.io/idta/SimulationModels/ModelFileVersion/1/0",
    "model_version_id": "https://admin-shell.io/idta/SimulationModels/ModelVersionId/1/0",
    "digital_file": "https://admin-shell.io/idta/SimulationModels/DigitalFile/1/0",
    "manufacturer_information": "https://admin-shell.io/idta/SimulationModels/SimModManufacturerInformation/1/0",
    "ports": "https://admin-shell.io/idta/SimulationModels/Ports/1/0",
    "ports_connector": "https://admin-shell.io/idta/SimulationModels/PortsConnector/1/0",
    "port_connector_name": "https://admin-shell.io/idta/SimulationModels/PortConnectorName/1/0",
    "variable": "https://admin-shell.io/idta/SimulationModels/Variable/1/0",
    "variable_name": "https://admin-shell.io/idta/SimulationModels/VariableName/1/0",
    "range": "https://admin-shell.io/idta/SimulationModels/Range/1/0",
    "variable_type": "https://admin-shell.io/idta/SimulationModels/VariableType/1/0",
    "variable_description": "https://admin-shell.io/idta/SimulationModels/VariableDescription/1/0",
    "unit_list": "https://admin-shell.io/idta/SimulationModels/UnitList/1/0",
    "unit_description": "https://admin-shell.io/idta/SimulationModels/UnitDescription/1/0",
    "variable_causality": "https://admin-shell.io/idta/SimulationModels/VariableCausality/1/0",
}

_FMI_VARIABLE_METADATA_EXTENSION = "decentralabs.fmi.variableMetadata.v1"

_MAX_FMI_VARIABLE_METADATA_BYTES = 262_144

def _validate_lab_id(lab_id: str) -> str:
    """Return a lab identifier safe to embed in an AAS resource identifier."""
    value = str(lab_id).strip()
    if _AAS_LAB_ID_RE.fullmatch(value) is None:
        raise ValueError("AAS lab ID is invalid")
    return value

def _aas_id_for_lab(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}"

def _submodel_id_for_fmu(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:simulationModels"

def _submodel_id_for_technical(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:technicalData"

def _submodel_id_for_execution(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:executionCapabilities"

def _submodel_id_for_interfaces(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:assetInterfaces"

def _submodel_id_for_contact(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:contactInformation"

def _submodel_id_for_handover(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:handoverDocumentation"

def _submodel_id_for_fmi_ls_related_resources(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:fmiLsRelatedResources"

def _submodel_id_for_access_control(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:simulationAccessControl"


def _encode_id(raw_id: str) -> str:
    """URL-encode an AAS/submodel ID for use in BaSyx V2 REST paths (base64url)."""
    return base64.urlsafe_b64encode(raw_id.encode()).decode().rstrip("=")

def _fmu_digest(fmu_path: Path, fmu_data_path: str | Path = FMU_DATA_PATH) -> str:
    """Return a digest for the configured-root FMU matching its filename.

    The caller supplies the already resolved FMU path to indicate that a hash
    is wanted, but the file to read is selected from directory entries below
    ``FMU_DATA_PATH``.  This keeps an arbitrary path from becoming a file
    system access in this module as well as in the runner.
    """
    try:
        base = Path(fmu_data_path).resolve()
        filename = fmu_path.name
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*\.fmu", filename, re.IGNORECASE):
            return ""

        def _find_match(directory: Path) -> Optional[Path]:
            try:
                entries = directory.iterdir()
            except OSError:
                return None
            for entry in entries:
                if os.path.normcase(entry.name) != os.path.normcase(filename):
                    continue
                try:
                    candidate = entry.resolve(strict=True)
                except OSError:
                    continue
                try:
                    candidate.relative_to(base)
                except ValueError:
                    continue
                if candidate.is_file():
                    return candidate
            return None

        candidate = _find_match(base)
        if candidate is None:
            for child in base.iterdir():
                if child.is_dir():
                    candidate = _find_match(child)
                    if candidate is not None:
                        break
        if candidate is None:
            return ""
        return hashlib.sha256(candidate.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return ""

_IDSHORT_UNSAFE_RE = re.compile(r"[^a-zA-Z0-9]+")

def _sanitize_idshort(name: str) -> str:
    """Convert an arbitrary string (e.g. a unit name) into a valid AAS idShort."""
    sanitized = _IDSHORT_UNSAFE_RE.sub("_", name).strip("_") or "Unit"
    if sanitized[0].isdigit():
        sanitized = "u" + sanitized
    return sanitized

def _fmi_type_to_idta(fmi_type: str) -> str:
    """Map FMI variable type to the IDTA 02005 variable type vocabulary."""
    mapping = {
        "Real": "Real",
        "Float64": "Real",
        "Float32": "Real",
        "Integer": "Integer",
        "Int32": "Integer",
        "Int16": "Integer",
        "Int64": "Integer",
        "UInt32": "Integer",
        "UInt16": "Integer",
        "UInt64": "Integer",
        "Boolean": "Boolean",
        "String": "String",
        "Enumeration": "ENUM",
    }
    return mapping.get(fmi_type, str(fmi_type or "Unknown"))

def _causality_to_port_type(causality: str) -> str:
    """Map FMI causality to IDTA port direction."""
    mapping = {
        "input": "Input",
        "output": "Output",
        "parameter": "Parameter",
        "calculatedParameter": "Parameter",
        "structuralParameter": "Parameter",
        "local": "Internal",
        "independent": "Internal",
    }
    return mapping.get(causality, "Internal")

def _fmi_causality_to_idta(causality: str) -> str:
    """Map FMI causalities onto IDTA 02005's Input/Output/Acausal values."""
    if causality == "output":
        return "Output"
    if causality in {"input", "parameter", "calculatedParameter", "structuralParameter"}:
        return "Input"
    return "Acausal"

def _semantic_id(value: str) -> dict:
    return {
        "type": "ExternalReference",
        "keys": [{"type": "GlobalReference", "value": value}],
    }

def _standard_property(id_short: str, value_type: str, value: object, semantic_id: str) -> dict:
    return {
        "idShort": id_short,
        "semanticId": _semantic_id(semantic_id),
        "modelType": "Property",
        "valueType": value_type,
        "value": str(value) if value is not None else "",
    }

def _standard_mlp(id_short: str, value: str, semantic_id: str) -> dict:
    return {
        "idShort": id_short,
        "semanticId": _semantic_id(semantic_id),
        "modelType": "MultiLanguageProperty",
        "value": [{"language": "en", "text": value}],
    }

def _arbitrary_property(id_short: str, value_type: str, value: object, description: str = "") -> dict:
    element = _standard_property(id_short, value_type, value, _SEMANTIC_ID_ARBITRARY)
    if description:
        element["description"] = [{"language": "en", "text": description}]
    return element

def _fmi_variable_metadata_extension(variable: dict) -> Optional[dict]:
    """Preserve FMI variable attributes not represented by IDTA 02005 fields.

    Standard port fields remain the interoperable representation for name,
    causality, type family, description, unit, and range. This versioned AAS
    Extension carries FMI-specific details that the template cannot express.
    """
    metadata_fields = (
        "type", "causality", "valueReference", "variability", "initial", "start", "nominal",
        "quantity", "displayName", "displayUnit", "dimensions", "enumItems", "declaredType",
    )
    metadata = {
        field: variable[field]
        for field in metadata_fields
        if field != "declaredType" and field in variable and variable[field] is not None
    }
    declared_type = variable.get("declaredType")
    if isinstance(declared_type, dict):
        # The effective unit, range, quantity and enumeration choices are
        # represented separately above or in IDTA's standard fields. Preserve
        # the FMI type alias identity without repeating those values.
        alias = {
            field: declared_type[field]
            for field in ("name", "type", "description")
            if isinstance(declared_type.get(field), str) and declared_type[field]
        }
        if alias:
            metadata["declaredType"] = alias
    if not metadata:
        return None

    encoded = json.dumps(metadata, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > _MAX_FMI_VARIABLE_METADATA_BYTES:
        raise ValueError("FMI variable metadata exceeds the AAS extension size limit")
    return {
        "name": _FMI_VARIABLE_METADATA_EXTENSION,
        "valueType": "xs:string",
        "value": encoded,
    }

def build_simulation_ports(variables: list[dict]) -> list[dict]:
    """Build the standard IDTA 02005 Ports/PortsConnector/Variable hierarchy."""
    grouped: dict[str, list[dict]] = {}
    for var in variables:
        causality = var.get("causality", "local")
        if causality == "local":
            continue
        grouped.setdefault(_causality_to_port_type(causality), []).append(var)

    connectors = []
    for connector_name, connector_variables in grouped.items():
        variable_elements = []
        for var in connector_variables:
            variable_name = str(var.get("name") or "Variable")
            variable_causality = var.get("causality", "local")
            variable_value = [
                _standard_property(
                    "VariableName", "xs:string", variable_name, _SIMULATION_SEMANTICS["variable_name"]
                ),
                _standard_property(
                    "VariableType", "xs:string", _fmi_type_to_idta(var.get("type", "Real")),
                    _SIMULATION_SEMANTICS["variable_type"],
                ),
                _standard_property(
                    "VariableCausality", "xs:string", _fmi_causality_to_idta(variable_causality),
                    _SIMULATION_SEMANTICS["variable_causality"],
                ),
            ]
            if var.get("description"):
                variable_value.append(
                    _standard_mlp(
                        "VariableDescription", str(var["description"]),
                        _SIMULATION_SEMANTICS["variable_description"],
                    )
                )
            unit = str(var.get("unit") or "").strip()
            variable_value.append(
                _standard_property("UnitList", "xs:string", "others", _SIMULATION_SEMANTICS["unit_list"])
            )
            if unit:
                variable_value.append(
                    _standard_mlp(
                        "UnitDescription", unit,
                        _SIMULATION_SEMANTICS["unit_description"],
                    )
                )
            if var.get("min") is not None or var.get("max") is not None:
                minimum = str(var["min"]) if var.get("min") is not None else ""
                maximum = str(var["max"]) if var.get("max") is not None else ""
                if minimum and maximum:
                    range_text = f"[{minimum}, {maximum}]"
                elif minimum:
                    range_text = f"[{minimum}, ∞)"
                else:
                    range_text = f"(-∞, {maximum}]"
                variable_value.append(
                    _standard_property("Range", "xs:string", range_text, _SIMULATION_SEMANTICS["range"])
                )
            variable_elements.append({
                "idShort": _sanitize_idshort(variable_name),
                "semanticId": _semantic_id(_SIMULATION_SEMANTICS["variable"]),
                "modelType": "SubmodelElementCollection",
                "value": variable_value,
                **({"extensions": [extension]} if (extension := _fmi_variable_metadata_extension(var)) else {}),
            })

        connectors.append({
            "idShort": _sanitize_idshort(connector_name),
            "semanticId": _semantic_id(_SIMULATION_SEMANTICS["ports_connector"]),
            "modelType": "SubmodelElementCollection",
            "value": [
                _standard_property(
                    "PortConnectorName", "xs:string", connector_name,
                    _SIMULATION_SEMANTICS["port_connector_name"],
                ),
                *variable_elements,
            ],
        })
    return connectors

def build_simulation_access_control_submodel(
    lab_id: str,
    metadata: dict,
    *,
    simulation_model_submodel_id: str | None = None,
) -> dict:
    """Build the Gateway's IDTA Part 4 JSON access-rule profile for an FMU."""
    access_rules = build_part4_access_rules(
        metadata,
        simulation_model_submodel_id or _submodel_id_for_fmu(lab_id),
    )
    encoded_rules = json.dumps(
        access_rules,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = fmi_interface_digest(metadata)
    generated_digest = hashlib.sha256(encoded_rules).hexdigest()
    return {
        "id": _submodel_id_for_access_control(lab_id),
        "idShort": "SimulationAccessControl",
        "semanticId": _semantic_id(_SEMANTIC_ID_SIMULATION_ACCESS_CONTROL),
        "modelType": "Submodel",
        "submodelElements": [
            _standard_property(
                "InterfaceDigest", "xs:string", digest,
                _SEMANTIC_ID_ACCESS_INTERFACE_DIGEST,
            ),
            _standard_property(
                "GeneratedPolicyDigest", "xs:string", generated_digest,
                _SEMANTIC_ID_ACCESS_GENERATED_DIGEST,
            ),
            {
                "idShort": "AllAccessPermissionRules",
                "modelType": "Blob",
                "contentType": "application/json",
                "value": base64.b64encode(encoded_rules).decode("ascii"),
            },
        ],
    }

def build_simulation_submodel(
    lab_id: str,
    access_key: str,
    metadata: dict,
    extra_info: Optional[dict] = None,
    *,
    fmu_path: Optional[Path] = None,
    fmu_data_path: str | Path = FMU_DATA_PATH,
) -> dict:
    """Build an IDTA 02005 v1.1 Provision of Simulation Models submodel.

    Provider contact and documentation are emitted into their dedicated standard
    submodels; this submodel only contains the simulation-model information.

    *fmu_path* is the filesystem path to the ``.fmu`` binary; when supplied a
    SHA-256 digest is computed and embedded in the ``ModelFile`` element.
    """
    submodel_id = _submodel_id_for_fmu(lab_id)

    # Summary is a standard IDTA 02005 MultiLanguageProperty.
    _description = (extra_info or {}).get("description", "").strip() or metadata.get("description", "").strip()
    sim_model_elements: list[dict] = []
    if _description:
        sim_model_elements.append(_standard_mlp("Summary", _description, _SIMULATION_SEMANTICS["summary"]))

    model_name = str(metadata.get("modelName") or "Unknown")
    model_collection = {
        "displayName": [{"language": "en", "text": model_name}],
    }
    model_type = metadata.get("simulationType") or metadata.get("simulationKind")
    if model_type:
        sim_model_elements.append(
            _standard_property("TypeOfModel", "xs:string", model_type, _SIMULATION_SEMANTICS["type_of_model"])
        )

    # ModelFile is a standard collection; DigitalFile is the only element that
    # points to the gateway resource. The access key is never published as a field.
    _fmu_sha256 = _fmu_digest(fmu_path, fmu_data_path) if fmu_path is not None else ""
    model_file_value: list[dict] = []
    fmi_version = str(metadata.get("fmiVersion") or "2.0")
    modes = []
    if metadata.get("supportsCoSimulation"):
        modes.append("Co-Simulation")
    if metadata.get("supportsModelExchange"):
        modes.append("Model Exchange")
    if not modes and metadata.get("simulationType"):
        modes.append(str(metadata["simulationType"]))
    model_file_value.append(_standard_property(
        "ModelFileType", "xs:string", ", ".join([f"FMI {fmi_version}", *modes]),
        _SIMULATION_SEMANTICS["model_file_type"],
    ))
    model_version = str(metadata.get("version") or "unversioned").strip() or "unversioned"
    digital_file: dict = {
        "idShort": "DigitalFile",
        "semanticId": _semantic_id(_SIMULATION_SEMANTICS["digital_file"]),
        "modelType": "File",
        "contentType": "application/zip",
        "value": f"/fmu-data/{access_key}",
    }
    if _fmu_sha256:
        digital_file["extensions"] = [{"name": "sha256", "valueType": "xs:string", "value": _fmu_sha256}]
    model_file_value.append({
        "idShort": "ModelFileVersion",
        "semanticId": _semantic_id(_SIMULATION_SEMANTICS["model_file_version"]),
        "modelType": "SubmodelElementCollection",
        "value": [
            _standard_property("ModelVersionId", "xs:string", model_version, _SIMULATION_SEMANTICS["model_version_id"]),
            digital_file,
        ],
    })
    sim_model_elements.append({
        "idShort": "ModelFile",
        "semanticId": _semantic_id(_SIMULATION_SEMANTICS["model_file"]),
        "modelType": "SubmodelElementCollection",
        "value": model_file_value,
    })

    raw_default_stop = metadata.get("defaultStopTime")
    if raw_default_stop is not None:
        default_start = float(metadata.get("defaultStartTime") or 0.0)
        default_stop = float(raw_default_stop)
        if default_stop > default_start:
            sim_model_elements.append(
                _standard_property("DefaultSimTime", "xs:double", default_stop - default_start, _SIMULATION_SEMANTICS["default_sim_time"])
            )

    # FMU tool and solver metadata have direct IDTA 02005 homes.
    _gen_tool = str(metadata.get("generationTool") or metadata.get("simulationTool") or "").strip()
    tolerance = metadata.get("defaultTolerance")
    fmi_capabilities = metadata.get("capabilities") or {}
    fixed_step = fmi_capabilities.get("fixedInternalStepSize")
    has_solver_metadata = (
        tolerance is not None
        or fixed_step is not None
        or bool(fmi_capabilities)
        or metadata.get("stiffSolverNeeded") is not None
    )
    if _gen_tool or has_solver_metadata:
        solver_elements = []
        if has_solver_metadata:
            solver_elements.extend([
                _standard_property(
                    "StepSizeControlNeeded", "xs:boolean", str(fixed_step is None).lower(),
                    "https://admin-shell.io/idta/SimulationModels/StepSizeControlNeeded/1/0",
                ),
                _standard_property(
                    "StiffSolverNeeded", "xs:boolean",
                    str(bool(metadata.get("stiffSolverNeeded", fmi_capabilities.get("stiffSolverNeeded", False)))).lower(),
                    "https://admin-shell.io/idta/SimulationModels/StiffSolverNeeded/1/0",
                ),
                _standard_property(
                    "SolverIncluded", "xs:boolean", str(bool(metadata.get("supportsCoSimulation"))).lower(),
                    "https://admin-shell.io/idta/SimulationModels/SolverIncluded/1/0",
                ),
            ])
        if fixed_step is not None:
            solver_elements.append(_standard_property("FixedStepSize", "xs:double", fixed_step, _SIMULATION_SEMANTICS["fixed_step_size"]))
        if tolerance is not None:
            solver_elements.append(_standard_property("Tolerance", "xs:double", tolerance, _SIMULATION_SEMANTICS["tolerance"]))
        simulation_tool_elements = [
            _standard_property("SimToolName", "xs:string", _gen_tool or "FMI runtime", _SIMULATION_SEMANTICS["sim_tool_name"]),
        ]
        if solver_elements:
            simulation_tool_elements.append({
                "idShort": "SolverAndTolerances",
                "semanticId": _semantic_id(_SIMULATION_SEMANTICS["solver"]),
                "modelType": "SubmodelElementCollection",
                "value": solver_elements,
            })
        sim_model_elements.append({
            "idShort": "Environment",
            "semanticId": _semantic_id(_SIMULATION_SEMANTICS["environment"]),
            "modelType": "SubmodelElementCollection",
            "value": [
                _standard_property(
                    "OperatingSystem", "xs:string", metadata.get("operatingSystem") or platform.platform(),
                    "https://admin-shell.io/idta/SimulationModels/OperatingSystem/1/0",
                ),
                {
                    "idShort": "SimulationTool",
                    "semanticId": _semantic_id(_SIMULATION_SEMANTICS["simulation_tool"]),
                    "modelType": "SubmodelElementCollection",
                    "value": simulation_tool_elements,
                }
            ],
        })

    license_model = str((extra_info or {}).get("license") or metadata.get("license") or "").strip()
    if license_model:
        sim_model_elements.append(_standard_property("LicenseModel", "xs:string", license_model, _SIMULATION_SEMANTICS["license_model"]))

    author = str(metadata.get("author") or "").strip()
    contact_email = str((extra_info or {}).get("contactEmail") or "").strip()
    if author or contact_email:
        manufacturer_values = []
        manufacturer_values.append(_standard_property(
            "Company", "xs:string", author or "DecentraLabs", "0173-1#02-AAW001#001"
        ))
        manufacturer_values.append(_standard_property(
            "Language", "xs:string", str(metadata.get("language") or "en"), "0173-1#02-AAO895#003"
        ))
        if contact_email:
            manufacturer_values.append({
                "idShort": "Email",
                "semanticId": _semantic_id("0173-1#02-AAQ836#005"),
                "modelType": "SubmodelElementCollection",
                "value": [
                    _standard_property("EmailAddress", "xs:string", contact_email, "0173-1#02-AAO198#002"),
                ],
            })
        sim_model_elements.append({
            "idShort": "SimModManufacturerInformation",
            "semanticId": _semantic_id(_SIMULATION_SEMANTICS["manufacturer_information"]),
            "modelType": "SubmodelElementCollection",
            "value": manufacturer_values,
        })

    ports = build_simulation_ports(metadata.get("modelVariables", []))
    if ports:
        sim_model_elements.append({
            "idShort": "Ports",
            "semanticId": _semantic_id(_SIMULATION_SEMANTICS["ports"]),
            "modelType": "SubmodelElementCollection",
            "value": ports,
        })

    submodel = {
        "id": submodel_id,
        "idShort": "SimulationModels",
        "semanticId": _semantic_id(_SEMANTIC_ID_SIMULATION_MODELS),
        "modelType": "Submodel",
        "submodelElements": [
            {
                "idShort": "SimulationModel",
                "semanticId": _semantic_id(_SEMANTIC_ID_SIMULATION_MODEL),
                "modelType": "SubmodelElementCollection",
                "value": sim_model_elements,
                **model_collection,
            }
        ],
    }
    return submodel

def build_execution_capabilities_submodel(
    lab_id: str,
    metadata: dict,
    runtime_info: Optional[dict] = None,
) -> Optional[dict]:
    """Build the standard IDTA 02020 capability description for an FMU."""
    metadata = metadata or {}
    supports_cosimulation = bool(metadata.get("supportsCoSimulation"))
    supports_model_exchange = bool(metadata.get("supportsModelExchange"))
    can_run_batch = supports_cosimulation or supports_model_exchange

    capability_names: list[tuple[str, str]] = []
    if can_run_batch:
        capability_names.extend([
            ("RunSimulation", "Run a reservation-authorized batch FMU simulation."),
            ("CancelSimulation", "Cancel a reservation-authorized batch FMU simulation."),
        ])

    if supports_cosimulation:
        capability_names.extend([
            ("CreateRealtimeSession", "Create an authenticated FMI Co-Simulation session."),
            ("Initialize", "Initialize a co-simulation session."),
            ("Start", "Start a co-simulation session."),
            ("Pause", "Pause a co-simulation session."),
            ("Resume", "Resume a co-simulation session."),
            ("Reset", "Reset a co-simulation session."),
            ("Step", "Advance a co-simulation session by one communication step."),
            ("RunUntil", "Advance a co-simulation session to a target time."),
            ("SetInputs", "Set FMI input values in a co-simulation session."),
            ("GetOutputs", "Read FMI output values from a co-simulation session."),
            ("TerminateSession", "Terminate a co-simulation session."),
        ])

    containers = []
    for name, description in capability_names:
        containers.append({
            "idShort": f"CapabilityContainer_{_sanitize_idshort(name)}",
            "semanticId": _semantic_id("https://admin-shell.io/idta/CapabilityDescription/CapabilityContainer/1/0"),
            "modelType": "SubmodelElementCollection",
            "value": [{
                "idShort": name,
                "semanticId": _semantic_id("https://admin-shell.io/idta/CapabilityDescription/Capability/1/0"),
                "modelType": "Capability",
                "description": [{"language": "en", "text": description}],
            }],
        })

    fmi_capabilities = metadata.get("capabilities") or {}
    if fmi_capabilities:
        property_containers = []
        for name, value in fmi_capabilities.items():
            if isinstance(value, bool):
                value_type = "xs:boolean"
                serialized = str(value).lower()
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                value_type = "xs:double"
                serialized = value
            else:
                value_type = "xs:string"
                serialized = str(value)
            property_containers.append({
                "idShort": f"PropertyContainer_{_sanitize_idshort(name)}",
                "semanticId": _semantic_id("https://admin-shell.io/idta/CapabilityDescription/PropertyContainer/1/0"),
                "modelType": "SubmodelElementCollection",
                "value": [{
                    "idShort": "PropertyProperty",
                    "semanticId": _semantic_id("https://admin-shell.io/idta/CapabilityPropertyType/Property/1/0"),
                    "modelType": "Property",
                    "valueType": value_type,
                    "value": str(serialized),
                    "description": [{"language": "en", "text": f"FMI capability: {name}"}],
                }],
            })
        containers.append({
            "idShort": "CapabilityContainer_FMISimulation",
            "semanticId": _semantic_id("https://admin-shell.io/idta/CapabilityDescription/CapabilityContainer/1/0"),
            "modelType": "SubmodelElementCollection",
            "value": [
                {
                    "idShort": "FMISimulation",
                    "semanticId": _semantic_id("https://admin-shell.io/idta/CapabilityDescription/Capability/1/0"),
                    "modelType": "Capability",
                    "description": [{"language": "en", "text": "FMI capabilities reported by the simulation model."}],
                },
                {
                    "idShort": "PropertySet_FMICapabilities",
                    "semanticId": _semantic_id("https://admin-shell.io/idta/CapabilityDescription/PropertySet/1/0"),
                    "modelType": "SubmodelElementCollection",
                    "value": property_containers,
                },
            ],
        })

    if not containers:
        return None

    return {
        "id": _submodel_id_for_execution(lab_id),
        "idShort": "CapabilityDescription",
        "modelType": "Submodel",
        "semanticId": _semantic_id(_SEMANTIC_ID_CAPABILITY_DESCRIPTION),
        "submodelElements": [{
            "idShort": "CapabilitySet",
            "semanticId": _semantic_id("https://admin-shell.io/idta/CapabilityDescription/CapabilitySet/1/0"),
            "modelType": "SubmodelElementCollection",
            "value": containers,
        }],
    }

def _asset_interface_action(name: str, href: str, method: str = "POST", subprotocol: str = "") -> dict:
    form_values = [
        _standard_property("href", "xs:anyURI", href, "https://www.w3.org/2019/wot/hypermedia#hasTarget"),
        _standard_property("htv_methodName", "xs:string", method, "https://www.w3.org/2011/http#methodName"),
    ]
    if subprotocol:
        form_values.append(_standard_property(
            "subprotocol", "xs:string", subprotocol,
            "https://www.w3.org/2019/wot/hypermedia#forSubProtocol",
        ))
    return {
        "idShort": name,
        "semanticId": _semantic_id("https://www.w3.org/2019/wot/td#ActionAffordance"),
        "modelType": "SubmodelElementCollection",
        "value": [{
            "idShort": "forms",
            "semanticId": _semantic_id("https://www.w3.org/2019/wot/td#hasForm"),
            "modelType": "SubmodelElementCollection",
            "value": form_values,
        }],
    }

def build_asset_interfaces_description_submodel(
    lab_id: str,
    operations: Sequence[tuple[str, str, str, str]],
    *,
    title: str = "DecentraLabs FMU interface",
) -> Optional[dict]:
    """Describe gateway HTTP/WebSocket affordances using IDTA 02017 / WoT."""
    actions = [_asset_interface_action(name, href, method, subprotocol) for name, href, method, subprotocol in operations]
    if not actions:
        return None
    bearer_scheme = {
        "idShort": "bearer_sc",
        "semanticId": _semantic_id("https://www.w3.org/2019/wot/security#BearerSecurityScheme"),
        "modelType": "SubmodelElementCollection",
        "value": [
            _standard_property("scheme", "xs:string", "bearer", "https://www.w3.org/2019/wot/security#SecurityScheme"),
            _standard_property("name", "xs:string", "Authorization", "https://www.w3.org/2019/wot/security#name"),
            _standard_property("in", "xs:string", "header", "https://www.w3.org/2019/wot/security#in"),
        ],
    }
    endpoint_metadata = {
        "idShort": "EndpointMetadata",
        "semanticId": _semantic_id("https://admin-shell.io/idta/AssetInterfacesDescription/1/0/EndpointMetadata"),
        "modelType": "SubmodelElementCollection",
        "value": [
            _standard_property("base", "xs:anyURI", "/fmu/api/v1", "https://www.w3.org/2019/wot/td#baseURI"),
            _standard_property("contentType", "xs:string", "application/json", "https://www.w3.org/2019/wot/hypermedia#forContentType"),
            {
                "idShort": "securityDefinitions",
                "semanticId": _semantic_id("https://www.w3.org/2019/wot/security#definesSecurityScheme"),
                "modelType": "SubmodelElementCollection",
                "value": [bearer_scheme],
            },
        ],
    }
    interface = {
        "idShort": "InterfaceTemplateForHTTP",
        "semanticId": _semantic_id("https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Interface"),
        "modelType": "SubmodelElementCollection",
        "value": [
            _standard_property("title", "xs:string", title, "https://www.w3.org/2019/wot/td#title"),
            endpoint_metadata,
            {
                "idShort": "InteractionMetadata",
                "semanticId": _semantic_id("https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InteractionMetadata"),
                "modelType": "SubmodelElementCollection",
                "value": [{
                    "idShort": "actions",
                    "semanticId": _semantic_id("https://www.w3.org/2019/wot/td#ActionAffordance"),
                    "modelType": "SubmodelElementCollection",
                    "value": actions,
                }],
            },
        ],
    }
    return {
        "id": _submodel_id_for_interfaces(lab_id),
        "idShort": "AssetInterfacesDescription",
        "modelType": "Submodel",
        "semanticId": _semantic_id(_SEMANTIC_ID_ASSET_INTERFACES),
        "submodelElements": [interface],
    }

def build_contact_information_submodel(lab_id: str, extra_info: Optional[dict] = None) -> Optional[dict]:
    email = str((extra_info or {}).get("contactEmail") or "").strip()
    if not email:
        return None
    values = []
    values.append({
        "idShort": "Email",
        "semanticId": _semantic_id("0173-1#02-AAQ836#005"),
        "modelType": "SubmodelElementCollection",
        "value": [_standard_property("EmailAddress", "xs:string", email, "0173-1#02-AAO198#002")],
    })
    return {
        "id": _submodel_id_for_contact(lab_id),
        "idShort": "ContactInformations",
        "modelType": "Submodel",
        "semanticId": _semantic_id(_SEMANTIC_ID_CONTACT_INFORMATION),
        "submodelElements": [{
            "idShort": "ContactInformation",
            "semanticId": _semantic_id("https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/ContactInformation"),
            "modelType": "SubmodelElementCollection",
            "value": values,
        }],
    }

def _documentation_urls(extra_info: Optional[dict]) -> list[str]:
    values = (extra_info or {}).get("documentationUrls", [])
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except (TypeError, ValueError):
            values = []
    if not isinstance(values, list):
        values = []
    single = str((extra_info or {}).get("documentationUrl") or "").strip()
    if single:
        values.append(single)
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))

def build_handover_documentation_submodel(lab_id: str, extra_info: Optional[dict] = None) -> Optional[dict]:
    documents = []
    urls = _documentation_urls(extra_info)
    license_value = str((extra_info or {}).get("license") or "").strip()
    if license_value and (license_value.startswith("http://") or license_value.startswith("https://")):
        urls.insert(0, license_value)
    document_specs = [
        (url, "License terms" if url == license_value else f"Documentation {index + 1}", "application/octet-stream")
        for index, url in enumerate(dict.fromkeys(urls))
    ]
    asset_url = str((extra_info or {}).get("digitalTwinAssetUrl") or "").strip()
    if asset_url:
        app_asset = urlsplit(asset_url).path.startswith("/digital-twin-apps/")
        document_specs.append((
            asset_url,
            "Three.js digital twin application" if app_asset else "Digital twin GLB scene",
            "text/html" if app_asset else "model/gltf-binary",
        ))
    if not document_specs:
        return None
    for index, (url, title, content_type) in enumerate(document_specs):
        identifier = url or f"license:{license_value}"
        document_ids = {
            "idShort": "DocumentIds",
            "semanticId": _semantic_id("0173-1#02-ABI501#003"),
            "modelType": "SubmodelElementList",
            "typeValueListElement": "SubmodelElementCollection",
            "value": [{
                "idShort": "DocumentIdentifier_0",
                "semanticId": _semantic_id("0173-1#02-ABI501#003/0173-1#01-AHF580#003"),
                "modelType": "SubmodelElementCollection",
                "value": [
                    _standard_property("DocumentDomainId", "xs:string", urlsplit(url).hostname or "decentralabs", "0173-1#02-ABH994#003"),
                    _standard_property("DocumentIdentifier", "xs:string", identifier, "0173-1#02-AAO099#004"),
                ],
            }],
        }
        documents.append({
            "idShort": f"Document_{index}",
            "semanticId": _semantic_id("0173-1#02-ABI500#003/0173-1#01-AHF579#003"),
            "modelType": "SubmodelElementCollection",
            "value": [{
                **document_ids,
            }, {
                "idShort": "DocumentVersions",
                "semanticId": _semantic_id("0173-1#02-ABI503#003"),
                "modelType": "SubmodelElementList",
                "typeValueListElement": "SubmodelElementCollection",
                "value": [{
                    "idShort": "DocumentVersion_0",
                    "semanticId": _semantic_id("0173-1#02-ABI503#003/0173-1#01-AHF582#003"),
                    "modelType": "SubmodelElementCollection",
                    "value": [
                        {
                            "idShort": "Language",
                            "semanticId": _semantic_id("0173-1#02-AAN468#008"),
                            "modelType": "SubmodelElementList",
                            "typeValueListElement": "Property",
                            "valueTypeListElement": "xs:string",
                            "value": [{
                                "idShort": "Language_0",
                                "semanticId": _semantic_id("0173-1#02-AAN468#008"),
                                "modelType": "Property",
                                "valueType": "xs:string",
                                "value": "en",
                                "valueId": _semantic_id("0173-1#07-AAS045#003"),
                            }],
                        },
                        _standard_property("Version", "xs:string", "1.0", "0173-1#02-AAP003#005"),
                        _standard_mlp("Title", title, "0173-1#02-ABG940#003"),
                        {
                            "idShort": "DigitalFiles",
                            "semanticId": _semantic_id("0173-1#02-ABK126#002"),
                            "modelType": "SubmodelElementList",
                            "typeValueListElement": "File",
                            "value": [{
                                "idShort": "DigitalTwinScene" if content_type == "model/gltf-binary" else "DigitalFile",
                                "semanticId": _semantic_id("0173-1#02-ABK126#002"),
                                "modelType": "File",
                                "contentType": content_type,
                                "value": url,
                            }],
                        },
                    ],
                }],
            }],
        })
    return {
        "id": _submodel_id_for_handover(lab_id),
        "idShort": "HandoverDocumentation",
        "modelType": "Submodel",
        "semanticId": _semantic_id(_SEMANTIC_ID_HANDOVER_DOCUMENTATION),
        "submodelElements": [{
            "idShort": "Documents",
            "semanticId": _semantic_id("0173-1#02-ABI500#003"),
            "modelType": "SubmodelElementList",
            "typeValueListElement": "SubmodelElementCollection",
            "value": documents,
        }],
    }


def build_fmi_ls_related_resources_submodel(
    lab_id: str,
    related_resources: Optional[dict],
) -> Optional[dict]:
    """Project embedded FMI-LS-REF resource descriptors into a versioned AAS submodel."""
    if not isinstance(related_resources, dict):
        return None
    manifest_name = str(related_resources.get("manifestName") or "").strip()
    if manifest_name != "org.fmi-standard.fmi-ls-ref":
        return None

    def property_element(id_short: str, name: str, value: object, value_type: str = "xs:string") -> dict:
        return _standard_property(
            id_short,
            value_type,
            value,
            f"{_SEMANTIC_ID_FMI_LS_RELATED_RESOURCES}:{name}",
        )

    resource_elements: list[dict] = []
    used_id_shorts: set[str] = set()
    raw_resources = related_resources.get("resources")
    if isinstance(raw_resources, list):
        for resource in raw_resources[:128]:
            if not isinstance(resource, dict):
                continue
            source = str(resource.get("source") or "").strip()
            parsed_source = urlsplit(source)
            if (
                not source
                or len(source) > 2048
                or "\\" in source
                or "\x00" in source
                or source.startswith("/")
                or parsed_source.scheme
                or parsed_source.netloc
                or parsed_source.query
                or parsed_source.fragment
            ):
                continue

            role = str(resource.get("role") or "").strip()[:128]
            media_type = str(resource.get("type") or "").strip()[:256]
            description = str(resource.get("description") or "").strip()[:2048]
            digest = hashlib.sha256(f"{role}\0{media_type}\0{source}".encode("utf-8")).hexdigest()[:24]
            id_short = f"RelatedResource_{digest}"
            suffix = 2
            while id_short in used_id_shorts:
                id_short = f"RelatedResource_{digest}_{suffix}"
                suffix += 1
            used_id_shorts.add(id_short)

            labels = []
            raw_labels = resource.get("labels")
            if isinstance(raw_labels, list):
                for label_index, label in enumerate(raw_labels[:32]):
                    if not isinstance(label, dict):
                        continue
                    label_name = str(label.get("name") or "").strip()[:256]
                    if not label_name:
                        continue
                    label_description = str(label.get("description") or "").strip()[:1024]
                    labels.append({
                        "idShort": f"Label_{label_index + 1}",
                        "modelType": "SubmodelElementCollection",
                        "value": [
                            property_element("Name", "LabelName", label_name),
                            *([property_element("Description", "LabelDescription", label_description)] if label_description else []),
                        ],
                    })

            fields = [
                property_element("Role", "Role", role),
                property_element("MediaType", "MediaType", media_type),
                property_element("Source", "Source", source),
                property_element(
                    "AvailableInFmu",
                    "AvailableInFmu",
                    str(resource.get("availableInFmu") is True).lower(),
                    "xs:boolean",
                ),
            ]
            if description:
                fields.append(property_element("Description", "Description", description))
            if labels:
                fields.append({
                    "idShort": "Labels",
                    "semanticId": _semantic_id(f"{_SEMANTIC_ID_FMI_LS_RELATED_RESOURCES}:Labels"),
                    "modelType": "SubmodelElementList",
                    "typeValueListElement": "SubmodelElementCollection",
                    "value": labels,
                })
            resource_elements.append({
                "idShort": id_short,
                "semanticId": _semantic_id(f"{_SEMANTIC_ID_FMI_LS_RELATED_RESOURCES}:RelatedResource"),
                "modelType": "SubmodelElementCollection",
                "value": fields,
            })

    submodel_elements = [
        property_element("ManifestName", "ManifestName", manifest_name),
    ]
    manifest_version = str(related_resources.get("manifestVersion") or "").strip()[:64]
    if manifest_version:
        submodel_elements.append(property_element("ManifestVersion", "ManifestVersion", manifest_version))
    submodel_elements.append({
        "idShort": "Resources",
        "semanticId": _semantic_id(f"{_SEMANTIC_ID_FMI_LS_RELATED_RESOURCES}:Resources"),
        "modelType": "SubmodelElementList",
        "typeValueListElement": "SubmodelElementCollection",
        "value": resource_elements,
    })
    return {
        "id": _submodel_id_for_fmi_ls_related_resources(lab_id),
        "idShort": "FmiLsRelatedResources",
        "semanticId": _semantic_id(_SEMANTIC_ID_FMI_LS_RELATED_RESOURCES),
        "modelType": "Submodel",
        "submodelElements": submodel_elements,
    }

def _non_negative_int(value: object) -> str:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return ""
    return str(number) if number >= 0 else ""

def build_technical_data_submodel(
    lab_id: str,
    metadata: dict,
    runtime_info: Optional[dict] = None,
) -> dict:
    """Build IDTA 02003 v2.0.1 TechnicalData with standard arbitrary extensions.

    Runtime status and capacity are not covered by the generic technical-data
    vocabulary. They therefore live in the template's official
    ``TechnicalPropertyAreas`` arbitrary-property slot, with descriptions that
    preserve their meaning without inventing DecentraLabs semantic IDs.
    """
    runtime = runtime_info or {}
    raw_status = str(runtime.get("status") or "").strip().upper()
    status_map = {
        "UP": "Ready",
        "DEGRADED": "Degraded",
        "DOWN": "Unavailable",
    }
    resource_status = status_map.get(raw_status, "Unknown")
    ready_flag = "true" if raw_status == "UP" else ("false" if raw_status in {"DEGRADED", "DOWN"} else "")
    metadata_available = bool(metadata)
    now_iso = datetime.now(timezone.utc).isoformat()

    general_information = {
        "idShort": "GeneralInformation",
        "semanticId": _semantic_id("0173-1#02-ABK161#002/0173-1#01-AHX838#002"),
        "modelType": "SubmodelElementCollection",
        "value": [
            _standard_property("ManufacturerName", "xs:string", "DecentraLabs", "0173-1#02-AAO677#004"),
            _standard_mlp("ManufacturerProductDesignation", "FMU execution resource", "0173-1#02-AAW338#003"),
        ],
    }
    arbitrary_values = [
        _arbitrary_property("ResourceType", "xs:string", "FMU", "DecentraLabs resource classification."),
        _arbitrary_property("ResourceStatus", "xs:string", resource_status, "Current publication status."),
        _arbitrary_property("ModelAvailable", "xs:boolean", str(metadata_available).lower(), "Whether FMU metadata is available."),
        _arbitrary_property("ExecutionBackend", "xs:string", str(runtime.get("backendMode") or ""), "Configured FMU execution backend."),
        _arbitrary_property("RunnerStatus", "xs:string", str(runtime.get("status") or ""), "Raw runner health status."),
        _arbitrary_property("LastSyncTimestamp", "xs:dateTime", now_iso, "Timestamp of this AAS publication."),
    ]
    if ready_flag:
        arbitrary_values.append(
            _arbitrary_property("ReadyFlag", "xs:boolean", ready_flag, "Whether the FMU runner reports readiness.")
        )
    active_simulation_count = _non_negative_int(runtime.get("activeSimulationCount"))
    if active_simulation_count:
        arbitrary_values.append(
            _arbitrary_property(
                "ActiveSimulationCount",
                "xs:nonNegativeInteger",
                active_simulation_count,
                "Active batch simulations.",
            )
        )
    max_concurrent_simulations = _non_negative_int(runtime.get("maxConcurrentSimulations"))
    if max_concurrent_simulations:
        arbitrary_values.append(
            _arbitrary_property(
                "MaxConcurrentSimulations",
                "xs:nonNegativeInteger",
                max_concurrent_simulations,
                "Configured simulation concurrency limit.",
            )
        )
    elements = [
        general_information,
        {
            "idShort": "TechnicalPropertyAreas",
            "semanticId": _semantic_id("0173-1#02-ABK163#002"),
            "modelType": "SubmodelElementList",
            "typeValueListElement": "SubmodelElementCollection",
            "value": [{
                "idShort": "OperationalStatus",
                "semanticId": _semantic_id("0173-1#02-ABL358#002/0173-1#01-AHX773#002"),
                "modelType": "SubmodelElementCollection",
                "value": arbitrary_values,
            }],
        },
    ]

    return {
        "id": _submodel_id_for_technical(lab_id),
        "idShort": "TechnicalData",
        "modelType": "Submodel",
        "semanticId": {
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": _SEMANTIC_ID_TECHNICAL_DATA}],
        },
        "submodelElements": elements,
    }

def build_aas_shell(
    lab_id: str,
    access_key: str,
    metadata: dict,
    extra_info: Optional[dict] = None,
    extra_submodel_ids: Sequence[str] = (),
    fmi_ls_resources: Optional[dict] = None,
) -> dict:
    """Build the AAS shell JSON for BaSyx V2.

    *extra_info* may contain ``description`` (str) for a human-readable
    description of the asset, surfaced as the AAS shell ``description`` field.
    *extra_submodel_ids* lists IDs of additional provider-managed submodels.
    """
    aas_id = _aas_id_for_lab(lab_id)
    all_sm_ids = [
        _submodel_id_for_fmu(lab_id),
        _submodel_id_for_technical(lab_id),
    ]
    metadata = metadata or {}
    supports_execution = bool(
        metadata.get("supportsCoSimulation")
        or metadata.get("supportsModelExchange")
        or metadata.get("capabilities")
    )
    if supports_execution:
        all_sm_ids.append(_submodel_id_for_execution(lab_id))
    if metadata.get("supportsCoSimulation") or metadata.get("supportsModelExchange"):
        all_sm_ids.append(_submodel_id_for_interfaces(lab_id))
    if isinstance(metadata.get("modelVariables"), list):
        all_sm_ids.append(_submodel_id_for_access_control(lab_id))
    if str((extra_info or {}).get("contactEmail") or "").strip():
        all_sm_ids.append(_submodel_id_for_contact(lab_id))
    if (
        _documentation_urls(extra_info)
        or str((extra_info or {}).get("license") or "").strip().startswith(("http://", "https://"))
        or str((extra_info or {}).get("digitalTwinAssetUrl") or "").strip()
    ):
        all_sm_ids.append(_submodel_id_for_handover(lab_id))
    if build_fmi_ls_related_resources_submodel(lab_id, fmi_ls_resources) is not None:
        all_sm_ids.append(_submodel_id_for_fmi_ls_related_resources(lab_id))
    all_sm_ids.extend(extra_submodel_ids)

    shell = {
        "id": aas_id,
        "idShort": f"DecentraLabs_Lab_{lab_id}",
        "modelType": "AssetAdministrationShell",
        "assetInformation": {
            "assetKind": "Instance",
            "globalAssetId": aas_id,
        },
        "submodels": [
            {"type": "ModelReference", "keys": [{"type": "Submodel", "value": sm_id}]}
            for sm_id in all_sm_ids
        ],
    }

    description = (extra_info or {}).get("description", "").strip()
    if description:
        shell["description"] = [{"language": "en", "text": description}]

    return shell
