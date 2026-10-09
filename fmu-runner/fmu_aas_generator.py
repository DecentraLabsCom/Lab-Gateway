"""
AAS shell and submodel generator for FMU resources.

Generates BaSyx V2-compatible JSON payloads from FMU describe metadata,
following IDTA 02005 (Provision of Simulation Models) for the simulation submodel.
"""

import base64
import hashlib
import io
import json
import logging
import os
import platform
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger("fmu-runner.aas")


def _env_or_secret_file(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    path = os.getenv(f"{name}_FILE")
    if not path:
        return default
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        logger.warning("Unable to read secret file for %s", name)
        return default


# Empty default: if not configured (e.g. Lite mode gateways without --profile aas),
# sync_fmu_to_basyx returns a disabled result instead of attempting a connection.
BASYX_AAS_URL = os.getenv("BASYX_AAS_URL", "")
AAS_ALLOWED_HOSTS = os.getenv("AAS_ALLOWED_HOSTS", "")
AAS_SERVICE_TOKEN = _env_or_secret_file("AAS_SERVICE_TOKEN")
AAS_SERVICE_TOKEN_HEADER = os.getenv("AAS_SERVICE_TOKEN_HEADER", "Authorization")
_BUNDLED_AAS_URL = "http://basyx-aas-server:8081"
FMU_DATA_PATH = os.getenv("FMU_DATA_PATH", "/app/fmu-data")
_AAS_LAB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_AAS_ENCODED_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,1024}")
_AAS_COLLECTIONS = frozenset({"shells", "submodels"})
_AASX_MEDIA_TYPE = "application/asset-administration-shell-package+xml"
_AASX_MEDIA_TYPES = frozenset({
    _AASX_MEDIA_TYPE,
    "application/aasx+xml",
    "application/aas+zip",
})

_SEMANTIC_ID_SIMULATION_MODELS = "https://admin-shell.io/idta/SubmodelTemplate/SimulationModels/1/1"
_SEMANTIC_ID_SIMULATION_MODEL = "https://admin-shell.io/idta/SimulationModels/SimulationModel/1/1"
_SEMANTIC_ID_TECHNICAL_DATA = "0173-1#01-AHX837#002"
_SEMANTIC_ID_CAPABILITY_DESCRIPTION = "https://admin-shell.io/idta/SubmodelTemplate/CapabilityDescription/1/0"
_SEMANTIC_ID_ASSET_INTERFACES = "https://admin-shell.io/idta/AssetInterfacesDescription/1/1/Submodel"
_SEMANTIC_ID_CONTACT_INFORMATION = "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations"
_SEMANTIC_ID_HANDOVER_DOCUMENTATION = "0173-1#01-AHF578#003"
_SEMANTIC_ID_ARBITRARY = "https://admin-shell.io/SMT/General/Arbitrary"

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


def _aas_request_headers() -> dict[str, str]:
    """Return the dedicated AAS credential, rejecting unsafe external URLs."""
    endpoint = BASYX_AAS_URL.rstrip("/")
    if endpoint == _BUNDLED_AAS_URL:
        return {}

    parsed = urlsplit(endpoint)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("external AAS endpoint must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("external AAS endpoint must not contain userinfo")

    allowed = {
        value.strip().lower()
        for value in AAS_ALLOWED_HOSTS.split(",")
        if value.strip()
    }
    if parsed.hostname.lower() not in allowed:
        raise ValueError("external AAS hostname is not allowlisted")
    if not AAS_SERVICE_TOKEN or AAS_SERVICE_TOKEN.strip().lower() in {
        "change_me",
        "changeme",
        "password",
        "test",
    }:
        raise ValueError("AAS_SERVICE_TOKEN is missing")

    header_name = (AAS_SERVICE_TOKEN_HEADER or "Authorization").strip()
    if not header_name or not all(
        (char.isalnum() or char == "-") for char in header_name
    ) or not header_name[0].isalpha():
        raise ValueError("invalid AAS_SERVICE_TOKEN_HEADER")
    value = AAS_SERVICE_TOKEN
    if header_name.lower() == "authorization":
        value = f"Bearer {value}"
    return {header_name: value}


def _validate_lab_id(lab_id: str) -> str:
    """Return a lab identifier safe to embed in an AAS resource identifier."""
    value = str(lab_id).strip()
    if _AAS_LAB_ID_RE.fullmatch(value) is None:
        raise ValueError("AAS lab ID is invalid")
    return value


def _aas_resource_path(collection: str, encoded_id: str) -> str:
    """Build a BaSyx resource path from an encoded, single-segment ID."""
    if collection not in _AAS_COLLECTIONS or _AAS_ENCODED_ID_RE.fullmatch(encoded_id) is None:
        raise ValueError("AAS resource path is invalid")
    return f"/{collection}/{encoded_id}"


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


def _fmu_digest(fmu_path: Path) -> str:
    """Return a digest for the configured-root FMU matching its filename.

    The caller supplies the already resolved FMU path to indicate that a hash
    is wanted, but the file to read is selected from directory entries below
    ``FMU_DATA_PATH``.  This keeps an arbitrary path from becoming a file
    system access in this module as well as in the runner.
    """
    try:
        base = Path(FMU_DATA_PATH).resolve()
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


def _encode_id(raw_id: str) -> str:
    """URL-encode an AAS/submodel ID for use in BaSyx V2 REST paths (base64url)."""
    return base64.urlsafe_b64encode(raw_id.encode()).decode().rstrip("=")


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
        "Enumeration": "Enumeration",
    }
    return mapping.get(fmi_type, "Real")


def _causality_to_port_type(causality: str) -> str:
    """Map FMI causality to IDTA port direction."""
    mapping = {
        "input": "Input",
        "output": "Output",
        "parameter": "Parameter",
        "calculatedParameter": "Parameter",
        "local": "Internal",
        "independent": "Internal",
    }
    return mapping.get(causality, "Internal")


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


def build_simulation_ports(variables: list[dict]) -> list[dict]:
    """Build the standard IDTA 02005 Ports/PortsConnector/Variable hierarchy."""
    grouped: dict[str, list[dict]] = {}
    for var in variables:
        causality = var.get("causality", "local")
        if causality in ("local", "independent"):
            continue
        grouped.setdefault(_causality_to_port_type(causality), []).append(var)

    connectors = []
    for connector_name, connector_variables in grouped.items():
        variable_elements = []
        for var in connector_variables:
            variable_name = str(var.get("name") or "Variable")
            variable_value = [
                _standard_property(
                    "VariableName", "xs:string", variable_name, _SIMULATION_SEMANTICS["variable_name"]
                ),
                _standard_property(
                    "VariableType", "xs:string", _fmi_type_to_idta(var.get("type", "Real")),
                    _SIMULATION_SEMANTICS["variable_type"],
                ),
                _standard_property(
                    "VariableCausality", "xs:string", var.get("causality", "local"),
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
                _standard_property("UnitList", "xs:string", unit or "others", _SIMULATION_SEMANTICS["unit_list"])
            )
            unit_description = var.get("displayUnit") or var.get("quantity")
            if unit_description:
                variable_value.append(
                    _standard_mlp(
                        "UnitDescription", str(unit_description),
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


def build_simulation_submodel(
    lab_id: str,
    access_key: str,
    metadata: dict,
    extra_info: Optional[dict] = None,
    *,
    fmu_path: Optional[Path] = None,
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
    _fmu_sha256 = _fmu_digest(fmu_path) if fmu_path is not None else ""
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

    default_start = float(metadata.get("defaultStartTime", 0.0) or 0.0)
    default_stop = float(metadata.get("defaultStopTime", 1.0) or 1.0)
    if default_stop >= default_start:
        sim_model_elements.append(
            _standard_property("DefaultSimTime", "xs:double", default_stop - default_start, _SIMULATION_SEMANTICS["default_sim_time"])
        )

    # FMU tool and solver metadata have direct IDTA 02005 homes.
    _gen_tool = str(metadata.get("generationTool") or metadata.get("simulationTool") or "").strip()
    tolerance = metadata.get("defaultTolerance")
    fmi_capabilities = metadata.get("capabilities") or {}
    fixed_step = fmi_capabilities.get("fixedInternalStepSize")
    if fixed_step is None:
        fixed_step = metadata.get("defaultStepSize")
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
    document_specs = [(url, "License terms" if url == license_value else f"Documentation {index + 1}")
                      for index, url in enumerate(dict.fromkeys(urls))]
    if not document_specs:
        return None
    for index, (url, title) in enumerate(document_specs):
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
                                "idShort": "DigitalFile",
                                "semanticId": _semantic_id("0173-1#02-ABK126#002"),
                                "modelType": "File",
                                "contentType": "application/octet-stream",
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
    if str((extra_info or {}).get("contactEmail") or "").strip():
        all_sm_ids.append(_submodel_id_for_contact(lab_id))
    if _documentation_urls(extra_info) or str((extra_info or {}).get("license") or "").strip().startswith(("http://", "https://")):
        all_sm_ids.append(_submodel_id_for_handover(lab_id))
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


def _parse_aasx(aasx_bytes: bytes) -> dict:
    """
    Parse an AASX package (ZIP/OPC container) and extract the AAS environment.

    AASX is a ZIP archive with a ``_rels/.rels`` relationship file pointing to
    the AAS origin part (typically a JSON or XML file).  Returns a dict with
    ``shells``, ``submodels``, and ``conceptDescriptions`` lists.
    """
    shells: list = []
    submodels: list = []
    concept_descs: list = []

    try:
        with zipfile.ZipFile(io.BytesIO(aasx_bytes)) as zf:
            names = set(zf.namelist())

            # Step 1: follow _rels/.rels to find the AAS origin part
            origin_path: Optional[str] = None
            rels_path = "_rels/.rels"
            if rels_path in names:
                try:
                    root = ET.fromstring(zf.read(rels_path))
                    ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
                    for rel in root.findall("r:Relationship", ns):
                        rel_type = rel.get("Type", "")
                        if "aasx-origin" in rel_type or "aas-spec" in rel_type:
                            target = rel.get("Target", "").lstrip("/")
                            if target in names:
                                origin_path = target
                                break
                except ET.ParseError:
                    # A malformed relationships part can be handled by JSON fallback scanning.
                    pass

            # Step 2: candidates — origin part first, then JSON scan fallback
            candidates: list = [origin_path] if origin_path else []
            if not candidates:
                candidates = [n for n in names if n.lower().endswith(".json") and not n.startswith("[")]

            for candidate in candidates:
                if not candidate or candidate not in names:
                    continue
                try:
                    data = json.loads(zf.read(candidate))
                    if "assetAdministrationShells" in data or "submodels" in data:
                        shells = data.get("assetAdministrationShells", [])
                        submodels = data.get("submodels", [])
                        concept_descs = data.get("conceptDescriptions", [])
                        break
                except (json.JSONDecodeError, KeyError):
                    continue
    except zipfile.BadZipFile:
        logger.error("AASX upload: not a valid ZIP/AASX file")

    return {"shells": shells, "submodels": submodels, "conceptDescriptions": concept_descs}


async def delete_aasx_resources(
    *,
    shell_ids: Sequence[str],
    submodel_ids: Sequence[str],
) -> dict:
    """Delete the resources imported from a provider AASX package.

    BaSyx DELETE is treated as idempotent: an already missing resource (404)
    is considered removed. Submodels are deleted before shells so the shell is
    never left referencing resources that this package owns. The caller can
    keep the local package catalog when the result contains ``error``.
    """
    result: dict = {
        "deletedAasIds": [],
        "deletedSubmodelIds": [],
        "failed": [],
    }
    operations: list[tuple[str, str, str]] = []
    for collection, ids in (
        ("submodels", submodel_ids or []),
        ("shells", shell_ids or []),
    ):
        for raw_id in ids:
            resource_id = str(raw_id or "").strip()
            try:
                path = _aas_resource_path(collection, _encode_id(resource_id))
            except (AttributeError, ValueError):
                result["failed"].append({
                    "collection": collection,
                    "id": resource_id,
                    "status": 400,
                })
                continue
            operations.append((collection, resource_id, path))

    if result["failed"]:
        result["error"] = "BaSyx resource deletion failed"
        return result
    if not operations:
        return result
    if not BASYX_AAS_URL:
        result["disabled"] = True
        result["error"] = "BaSyx is not configured"
        return result

    try:
        async with httpx.AsyncClient(
            base_url=BASYX_AAS_URL,
            headers=_aas_request_headers(),
            timeout=15.0,
        ) as client:
            for collection, resource_id, path in operations:
                response = await client.delete(path)
                if response.status_code in (200, 202, 204, 404):
                    result[
                        "deletedAasIds" if collection == "shells" else "deletedSubmodelIds"
                    ].append(resource_id)
                else:
                    result["failed"].append({
                        "collection": collection,
                        "id": resource_id,
                        "status": response.status_code,
                    })
    except httpx.RequestError as exc:
        logger.warning(
            "BaSyx unreachable while deleting AASX resources at %s: %s",
            str(BASYX_AAS_URL).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        result["error"] = "BaSyx unreachable"
        return result
    except ValueError as exc:
        logger.error(
            "AAS endpoint policy rejected deletion at %s: %s",
            str(BASYX_AAS_URL).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        result["error"] = "AAS endpoint policy rejected"
        return result

    if result["failed"]:
        result["error"] = "BaSyx resource deletion failed"
    return result


async def serialize_aasx_resources(
    *,
    shell_ids: Sequence[str],
    submodel_ids: Sequence[str],
) -> dict:
    """Generate an AASX package from the current resources in BaSyx."""
    encoded_shell_ids: list[str] = []
    encoded_submodel_ids: list[str] = []
    try:
        for raw_id in shell_ids or []:
            resource_id = str(raw_id or "").strip()
            encoded_id = _encode_id(resource_id)
            if not resource_id or _AAS_ENCODED_ID_RE.fullmatch(encoded_id) is None:
                raise ValueError("AAS shell resource ID is invalid")
            if encoded_id not in encoded_shell_ids:
                encoded_shell_ids.append(encoded_id)
        for raw_id in submodel_ids or []:
            resource_id = str(raw_id or "").strip()
            encoded_id = _encode_id(resource_id)
            if not resource_id or _AAS_ENCODED_ID_RE.fullmatch(encoded_id) is None:
                raise ValueError("AAS submodel resource ID is invalid")
            if encoded_id not in encoded_submodel_ids:
                encoded_submodel_ids.append(encoded_id)
    except (AttributeError, ValueError) as exc:
        return {"error": str(exc)}

    if not encoded_shell_ids and not encoded_submodel_ids:
        return {"error": "AASX package has no BaSyx resource IDs"}
    if not BASYX_AAS_URL:
        result = {"disabled": True, "error": "BaSyx is not configured"}
        return result

    params: list[tuple[str, str]] = [
        ("aasIds", encoded_id)
        for encoded_id in encoded_shell_ids
    ]
    params.append(("includeConceptDescriptions", "true"))
    params.extend(("submodelIds", encoded_id) for encoded_id in encoded_submodel_ids)

    try:
        async with httpx.AsyncClient(
            base_url=BASYX_AAS_URL,
            headers=_aas_request_headers(),
            timeout=30.0,
        ) as client:
            response = await client.get(
                "/serialization",
                params=params,
                headers={"Accept": _AASX_MEDIA_TYPE},
            )
            if response.status_code != 200:
                logger.warning("BaSyx AASX serialization failed: status=%s", response.status_code)
                return {"error": f"BaSyx serialization failed: {response.status_code}"}

            content = bytes(response.content or b"")
            content_type = (
                response.headers.get("content-type", "") or _AASX_MEDIA_TYPE
            ).split(";", 1)[0].strip().lower()
            if content_type not in _AASX_MEDIA_TYPES:
                logger.warning("BaSyx returned a non-AASX serialization content type")
                return {"error": "BaSyx serialization returned an invalid content type"}
            if not content.startswith(b"PK\x03\x04"):
                logger.warning("BaSyx returned an invalid AASX archive")
                return {"error": "BaSyx serialization returned an invalid archive"}
            return {
                "content": content,
                "mediaType": content_type or _AASX_MEDIA_TYPE,
            }
    except httpx.RequestError as exc:
        logger.warning(
            "BaSyx unreachable while serializing AASX at %s: %s",
            str(BASYX_AAS_URL).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        return {"error": "BaSyx unreachable"}
    except ValueError as exc:
        logger.error(
            "AAS endpoint policy rejected serialization at %s: %s",
            str(BASYX_AAS_URL).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        return {"error": "AAS endpoint policy rejected"}


def _aas_collection_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        candidates = []
        for key in ("result", "shells", "items", "value"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
        if not candidates and isinstance(payload.get("id"), str):
            candidates = [payload]
    else:
        candidates = []
    return [item for item in candidates if isinstance(item, dict)]


def _shell_submodel_ids(shell: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for reference in shell.get("submodels", []) if isinstance(shell.get("submodels"), list) else []:
        values: list[Any] = []
        if isinstance(reference, str):
            values.append(reference)
        elif isinstance(reference, dict):
            if isinstance(reference.get("id"), str):
                values.append(reference["id"])
            keys = reference.get("keys")
            if isinstance(keys, list):
                values.extend(
                    key.get("value")
                    for key in keys
                    if isinstance(key, dict) and isinstance(key.get("value"), str)
                )
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
    return result


def _find_property_value(payload: Any, id_short: str) -> Optional[str]:
    """Find a scalar Property value in a nested AAS element payload."""
    if isinstance(payload, dict):
        if (
            payload.get("modelType") == "Property"
            and payload.get("idShort") == id_short
            and payload.get("value") is not None
        ):
            value = str(payload.get("value")).strip()
            return value or None
        for child in payload.values():
            found = _find_property_value(child, id_short)
            if found:
                return found
    elif isinstance(payload, list):
        for child in payload:
            found = _find_property_value(child, id_short)
            if found:
                return found
    return None


async def _generated_updated_at(
    client: httpx.AsyncClient,
    lab_id: str,
    submodel_ids: list[str],
) -> Optional[str]:
    """Read the generated TechnicalData publication timestamp when present."""
    technical_id = _submodel_id_for_technical(lab_id)
    if technical_id not in submodel_ids:
        return None
    try:
        response = await client.get(f"/submodels/{_encode_id(technical_id)}")
    except httpx.RequestError:
        return None
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return None
    return _find_property_value(payload, "LastSyncTimestamp")


async def discover_basyx_shells() -> dict[str, Any]:
    """Discover current provider shells for the Lab Manager association view."""
    if not BASYX_AAS_URL:
        return {"disabled": True, "shells": []}

    try:
        async with httpx.AsyncClient(
            base_url=BASYX_AAS_URL,
            headers=_aas_request_headers(),
            timeout=15.0,
        ) as client:
            response = await client.get("/shells")
            if response.status_code != 200:
                logger.warning("BaSyx shell discovery failed: status=%s", response.status_code)
                return {"error": "BaSyx shell discovery failed"}

            discovered: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for shell in _aas_collection_items(response.json()):
                shell_id = shell.get("id")
                if not isinstance(shell_id, str) or not shell_id.startswith("urn:decentralabs:lab:"):
                    continue
                submodel_ids = [
                    value.strip()
                    for value in (
                        shell.get("submodelIds")
                        if isinstance(shell.get("submodelIds"), list)
                        else _shell_submodel_ids(shell)
                    )
                    if isinstance(value, str) and value.strip()
                ]
                if not submodel_ids:
                    encoded_id = _encode_id(shell_id)
                    detail = await client.get(f"/shells/{encoded_id}")
                    if detail.status_code == 200:
                        detail_payload = detail.json()
                        if isinstance(detail_payload, dict):
                            submodel_ids = _shell_submodel_ids(detail_payload)
                if shell_id in seen_ids:
                    continue
                seen_ids.add(shell_id)
                generated_shell = {
                    "id": shell_id,
                    "submodelIds": list(dict.fromkeys(submodel_ids)),
                }
                lab_id = shell_id[len("urn:decentralabs:lab:"):]
                updated_at = await _generated_updated_at(
                    client,
                    lab_id,
                    generated_shell["submodelIds"],
                )
                if updated_at:
                    generated_shell["updatedAt"] = updated_at
                discovered.append(generated_shell)
            return {"shells": discovered}
    except httpx.RequestError as exc:
        logger.warning(
            "BaSyx unreachable while discovering shells at %s: %s",
            str(BASYX_AAS_URL).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        return {"error": "BaSyx unavailable"}
    except ValueError as exc:
        logger.error(
            "AAS endpoint policy rejected shell discovery at %s: %s",
            str(BASYX_AAS_URL).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        return {"error": "AAS endpoint policy rejected"}


async def sync_fmu_to_basyx(
    lab_id: str,
    access_key: str,
    metadata: dict,
    aasx_bytes: Optional[bytes] = None,
    extra_info: Optional[dict] = None,
    fmu_path: Optional[Path] = None,
    unit_definitions: Sequence[dict] = (),
    required_aas_id: Optional[str] = None,
    runtime_info: Optional[dict] = None,
) -> dict:
    """
    Create or update the AAS shell and generated FMU submodels in BaSyx.

    If *aasx_bytes* is provided the package is parsed and every shell /
    submodel it contains is uploaded to BaSyx via the standard JSON REST
    API (PUT, fallback POST).  When *aasx_bytes* is ``None`` the shell and
    submodel are auto-generated from *metadata*.

    Returns a summary dict with ids and status.
    """
    try:
        lab_id = _validate_lab_id(lab_id)
    except ValueError:
        return {"error": "AAS lab ID rejected", "created": False, "updated": False}

    aas_id = _aas_id_for_lab(lab_id)
    submodel_id = _submodel_id_for_fmu(lab_id)
    technical_data_id = _submodel_id_for_technical(lab_id)
    execution_capabilities_id = _submodel_id_for_execution(lab_id)
    interfaces_id = _submodel_id_for_interfaces(lab_id)
    contact_id = _submodel_id_for_contact(lab_id)
    handover_id = _submodel_id_for_handover(lab_id)

    result: dict = {
        "aasId": aas_id,
        "submodelId": submodel_id,
        "technicalDataSubmodelId": technical_data_id,
        "executionSubmodelId": execution_capabilities_id,
        "interfacesSubmodelId": interfaces_id,
        "contactSubmodelId": contact_id,
        "handoverSubmodelId": handover_id,
        "created": False,
        "updated": False,
    }

    if not BASYX_AAS_URL:
        logger.info("BASYX_AAS_URL not configured — AAS sync disabled (Lite or non-AAS gateway).")
        result["disabled"] = True
        return result

    try:
        async with httpx.AsyncClient(
            base_url=BASYX_AAS_URL,
            headers=_aas_request_headers(),
            timeout=15.0,
        ) as client:
            if aasx_bytes:
                # ── AASX path: parse package and upload contained resources ──
                env = _parse_aasx(aasx_bytes)
                all_shells = env.get("shells", [])
                all_submodels = env.get("submodels", [])

                if not all_shells and not all_submodels:
                    result["error"] = "AASX parse produced no shells or submodels"
                    return result

                required_shell_id = str(required_aas_id or "").strip()
                if required_shell_id and not any(
                    isinstance(shell, dict) and shell.get("id") == required_shell_id
                    for shell in all_shells
                ):
                    result["error"] = f"AASX must contain shell {required_shell_id}"
                    return result

                uploaded_aas_ids: list = []
                uploaded_sm_ids: list = []

                for shell in all_shells:
                    shell_enc = _encode_id(shell.get("id", ""))
                    if re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", shell_enc) is None:
                        raise ValueError("AAS shell resource ID is invalid")
                    r = await client.put(
                        f"/shells/{shell_enc}",
                        json=shell,
                        headers={"Content-Type": "application/json"},
                    )
                    if r.status_code in (200, 201, 204):
                        uploaded_aas_ids.append(shell.get("id", ""))
                        result["created" if r.status_code == 201 else "updated"] = True
                    else:
                        r2 = await client.post("/shells", json=shell, headers={"Content-Type": "application/json"})
                        if r2.status_code in (200, 201):
                            uploaded_aas_ids.append(shell.get("id", ""))
                            result["created"] = True
                        else:
                            logger.error("AASX shell upload failed: %s %s", r2.status_code, r2.text[:300])
                            result["error"] = f"shell upload failed: {r2.status_code}"
                            return result

                for submodel in all_submodels:
                    sm_enc = _encode_id(submodel.get("id", ""))
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", sm_enc):
                        raise ValueError("AAS submodel resource ID is invalid")
                    r = await client.put(
                        f"/submodels/{sm_enc}",
                        json=submodel,
                        headers={"Content-Type": "application/json"},
                    )
                    if r.status_code in (200, 201, 204):
                        uploaded_sm_ids.append(submodel.get("id", ""))
                        result["created" if r.status_code == 201 else "updated"] = True
                    else:
                        r2 = await client.post("/submodels", json=submodel, headers={"Content-Type": "application/json"})
                        if r2.status_code in (200, 201):
                            uploaded_sm_ids.append(submodel.get("id", ""))
                            result["created"] = True
                        else:
                            logger.error("AASX submodel upload failed: %s %s", r2.status_code, r2.text[:300])
                            result["error"] = f"submodel upload failed: {r2.status_code}"
                            return result

                result["aasxUpload"] = True
                result["uploadedAasIds"] = uploaded_aas_ids
                result["uploadedSubmodelIds"] = uploaded_sm_ids
                if uploaded_aas_ids:
                    result["aasId"] = uploaded_aas_ids[0]
                if uploaded_sm_ids:
                    result["submodelId"] = uploaded_sm_ids[0]

            else:
                # ── Metadata path: auto-generate shell + submodel from FMU ──
                aas_id_encoded = _encode_id(aas_id)
                submodel_id_encoded = _encode_id(submodel_id)
                technical_data_id_encoded = _encode_id(technical_data_id)

                shell_payload = build_aas_shell(lab_id, access_key, metadata, extra_info)
                submodel_payload = build_simulation_submodel(lab_id, access_key, metadata, extra_info, fmu_path=fmu_path)
                technical_data_payload = build_technical_data_submodel(lab_id, metadata, runtime_info)
                execution_capabilities_payload = build_execution_capabilities_submodel(
                    lab_id,
                    metadata,
                    runtime_info,
                )
                execution_operations = []
                if metadata.get("supportsCoSimulation") or metadata.get("supportsModelExchange"):
                    execution_operations.extend([
                        ("RunSimulation", "/fmu/api/v1/simulations/run", "POST", ""),
                        ("CancelSimulation", "/fmu/api/v1/simulations/{simulationId}/cancel", "POST", ""),
                    ])
                if metadata.get("supportsCoSimulation"):
                    execution_operations.extend([
                        ("CreateRealtimeSession", "/fmu/api/v1/fmu/sessions", "GET", "websocket"),
                        *[(command, "/fmu/api/v1/fmu/sessions", "GET", "websocket") for command in (
                            "Initialize", "Start", "Pause", "Resume", "Reset", "Step", "RunUntil",
                            "SetInputs", "GetOutputs", "TerminateSession",
                        )],
                    ])
                interfaces_payload = build_asset_interfaces_description_submodel(lab_id, execution_operations)
                contact_payload = build_contact_information_submodel(lab_id, extra_info)
                handover_payload = build_handover_documentation_submodel(lab_id, extra_info)

                # --- Submodel: PUT (create or replace) ---
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", submodel_id_encoded):
                    raise ValueError("AAS submodel resource ID is invalid")
                sm_resp = await client.put(
                    f"/submodels/{submodel_id_encoded}",
                    json=submodel_payload,
                    headers={"Content-Type": "application/json"},
                )
                if sm_resp.status_code == 201:
                    result["created"] = True
                    logger.info("Created simulation submodel")
                elif sm_resp.status_code in (200, 204):
                    result["updated"] = True
                    logger.info("Updated simulation submodel")
                else:
                    # Try POST if PUT-to-create isn't supported
                    if sm_resp.status_code == 404:
                        sm_post = await client.post(
                            "/submodels",
                            json=submodel_payload,
                            headers={"Content-Type": "application/json"},
                        )
                        if sm_post.status_code in (200, 201):
                            result["created"] = True
                            logger.info("Created simulation submodel via POST")
                        else:
                            logger.error("Failed to create simulation submodel: status=%s", sm_post.status_code)
                            result["error"] = f"submodel creation failed: {sm_post.status_code}"
                            return result
                    else:
                        logger.error("Failed to update simulation submodel: status=%s", sm_resp.status_code)
                        result["error"] = f"submodel sync failed: {sm_resp.status_code}"
                        return result

                # --- Common TechnicalData submodel ---
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", technical_data_id_encoded):
                    raise ValueError("AAS technical data resource ID is invalid")
                td_resp = await client.put(
                    f"/submodels/{technical_data_id_encoded}",
                    json=technical_data_payload,
                    headers={"Content-Type": "application/json"},
                )
                if td_resp.status_code == 201:
                    result["created"] = True
                    logger.info("Created TechnicalData submodel")
                elif td_resp.status_code in (200, 204):
                    result["updated"] = True
                    logger.info("Updated TechnicalData submodel")
                elif td_resp.status_code == 404:
                    td_post = await client.post(
                        "/submodels",
                        json=technical_data_payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if td_post.status_code in (200, 201):
                        result["created"] = True
                        logger.info("Created TechnicalData submodel via POST")
                    else:
                        logger.error("Failed to create TechnicalData submodel: status=%s", td_post.status_code)
                        result["error"] = f"technical data creation failed: {td_post.status_code}"
                        return result
                else:
                    logger.error("Failed to update TechnicalData submodel: status=%s", td_resp.status_code)
                    result["error"] = f"technical data sync failed: {td_resp.status_code}"
                    return result

                # --- CapabilityDescription submodel ---
                if execution_capabilities_payload is not None:
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", _encode_id(execution_capabilities_id)):
                        raise ValueError("AAS execution capabilities resource ID is invalid")
                    execution_resp = await client.put(
                        f"/submodels/{_encode_id(execution_capabilities_id)}",
                        json=execution_capabilities_payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if execution_resp.status_code == 201:
                        result["created"] = True
                        logger.info("Created CapabilityDescription submodel")
                    elif execution_resp.status_code in (200, 204):
                        result["updated"] = True
                        logger.info("Updated CapabilityDescription submodel")
                    elif execution_resp.status_code == 404:
                        execution_post = await client.post(
                            "/submodels",
                            json=execution_capabilities_payload,
                            headers={"Content-Type": "application/json"},
                        )
                        if execution_post.status_code in (200, 201):
                            result["created"] = True
                            logger.info("Created CapabilityDescription submodel via POST")
                        else:
                            logger.error(
                                "Failed to create CapabilityDescription submodel: status=%s",
                                execution_post.status_code,
                            )
                            result["error"] = f"execution capabilities creation failed: {execution_post.status_code}"
                            return result
                    else:
                        logger.error(
                            "Failed to update CapabilityDescription submodel: status=%s",
                            execution_resp.status_code,
                        )
                        result["error"] = f"execution capabilities sync failed: {execution_resp.status_code}"
                        return result

                # --- Standard interface/contact/handover submodels ---
                for _sm_id, _sm_payload, _label in (
                    (interfaces_id, interfaces_payload, "AssetInterfacesDescription"),
                    (contact_id, contact_payload, "ContactInformations"),
                    (handover_id, handover_payload, "HandoverDocumentation"),
                ):
                    if _sm_payload is None:
                        continue
                    _sm_enc = _encode_id(_sm_id)
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", _sm_enc):
                        raise ValueError(f"AAS {_label} resource ID is invalid")
                    _sm_resp = await client.put(
                        f"/submodels/{_sm_enc}",
                        json=_sm_payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if _sm_resp.status_code in (200, 201, 204):
                        logger.info("%s submodel synced", _label)
                    elif _sm_resp.status_code == 404:
                        _sm_post = await client.post(
                            "/submodels", json=_sm_payload,
                            headers={"Content-Type": "application/json"},
                        )
                        if _sm_post.status_code not in (200, 201):
                            result["error"] = f"{_label} creation failed: {_sm_post.status_code}"
                            return result
                    else:
                        result["error"] = f"{_label} sync failed: {_sm_resp.status_code}"
                        return result

                # --- Shell: PUT (create or replace) ---
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", aas_id_encoded):
                    raise ValueError("AAS shell resource ID is invalid")
                shell_resp = await client.put(
                    f"/shells/{aas_id_encoded}",
                    json=shell_payload,
                    headers={"Content-Type": "application/json"},
                )
                if shell_resp.status_code == 201:
                    logger.info("Created AAS shell")
                elif shell_resp.status_code in (200, 204):
                    logger.info("Updated AAS shell")
                else:
                    if shell_resp.status_code == 404:
                        shell_post = await client.post(
                            "/shells",
                            json=shell_payload,
                            headers={"Content-Type": "application/json"},
                        )
                        if shell_post.status_code in (200, 201):
                            logger.info("Created AAS shell via POST")
                        else:
                            logger.error("Failed to create AAS shell: status=%s", shell_post.status_code)
                            result["error"] = f"shell creation failed: {shell_post.status_code}"
                            return result
                    else:
                        logger.error("Failed to update AAS shell: status=%s", shell_resp.status_code)
                        result["error"] = f"shell sync failed: {shell_resp.status_code}"
                        return result

    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning(
            "BaSyx unreachable at %s: %s",
            str(BASYX_AAS_URL).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        result["error"] = "BaSyx unreachable"
        return result
    except ValueError as exc:
        logger.error(
            "AAS endpoint policy rejected %s: %s",
            str(BASYX_AAS_URL).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        result["error"] = "AAS endpoint policy rejected"
        return result

    result["synced"] = True
    return result
