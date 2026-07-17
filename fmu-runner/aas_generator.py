"""
AAS shell and submodel generator for FMU resources.

Generates BaSyx V2-compatible JSON payloads from FMU describe metadata,
following IDTA 02006 (Provision of Simulation Models) for the simulation submodel.
"""

import base64
import hashlib
import io
import json
import logging
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger("fmu-runner.aas")

# Empty default: if not configured (e.g. Lite mode gateways without --profile aas),
# sync_fmu_to_basyx returns a disabled result instead of attempting a connection.
BASYX_AAS_URL = os.getenv("BASYX_AAS_URL", "")
AAS_ALLOWED_HOSTS = os.getenv("AAS_ALLOWED_HOSTS", "")
AAS_SERVICE_TOKEN = os.getenv("AAS_SERVICE_TOKEN", "")
AAS_SERVICE_TOKEN_HEADER = os.getenv("AAS_SERVICE_TOKEN_HEADER", "Authorization")
_BUNDLED_AAS_URL = "http://basyx-aas-server:8081"
FMU_DATA_PATH = os.getenv("FMU_DATA_PATH", "/app/fmu-data")
_AAS_LAB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_AAS_ENCODED_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,1024}")
_AAS_COLLECTIONS = frozenset({"shells", "submodels"})

_SEMANTIC_ID_IDTA_02006 = "https://admin-shell.io/idta/SimulationModels/SimulationModels/1/0"
_SEMANTIC_ID_SIMULATION_MODEL = "https://admin-shell.io/idta/SimulationModels/SimulationModel/1/0"
_SEMANTIC_ID_SIMULATION_MODEL_PORT = "https://admin-shell.io/idta/SimulationModels/PortsInformation/Port/1/0"


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


def _unit_submodel_id_for_lab(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:unitDefinitions"


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
    """Map FMI variable type to IDTA 02006 data type string."""
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


def build_simulation_ports(variables: list[dict]) -> list[dict]:
    """Build IDTA 02006 port submodel elements from FMU model variables."""
    ports = []
    for var in variables:
        causality = var.get("causality", "local")
        if causality in ("local", "independent"):
            continue

        port_element = {
            "idShort": var["name"],
            "semanticId": {
                "type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": _SEMANTIC_ID_SIMULATION_MODEL_PORT}],
            },
            "modelType": "SubmodelElementCollection",
            "value": [
                {"idShort": "PortCausality", "modelType": "Property", "valueType": "xs:string", "value": _causality_to_port_type(causality)},
                {"idShort": "PortDataType", "modelType": "Property", "valueType": "xs:string", "value": _fmi_type_to_idta(var.get("type", "Real"))},
                {"idShort": "PortVariability", "modelType": "Property", "valueType": "xs:string", "value": var.get("variability", "continuous")},
            ],
        }

        if "unit" in var:
            port_element["value"].append(
                {"idShort": "Unit", "modelType": "Property", "valueType": "xs:string", "value": var["unit"]}
            )
        if "start" in var:
            port_element["value"].append(
                {"idShort": "DefaultValue", "modelType": "Property", "valueType": "xs:string", "value": str(var["start"])}
            )
        if var.get("quantity"):
            port_element["value"].append(
                {"idShort": "QuantityKind", "modelType": "Property", "valueType": "xs:string", "value": var["quantity"]}
            )
        if var.get("displayUnit"):
            port_element["value"].append(
                {"idShort": "DisplayUnit", "modelType": "Property", "valueType": "xs:string", "value": var["displayUnit"]}
            )
        if var.get("nominal") is not None:
            port_element["value"].append(
                {"idShort": "NominalValue", "modelType": "Property", "valueType": "xs:string", "value": str(var["nominal"])}
            )
        if var.get("description"):
            port_element["value"].append(
                {"idShort": "PortDescription", "modelType": "Property", "valueType": "xs:string", "value": var["description"]}
            )

        ports.append(port_element)
    return ports


def build_simulation_submodel(
    lab_id: str,
    access_key: str,
    metadata: dict,
    extra_info: Optional[dict] = None,
    *,
    fmu_path: Optional[Path] = None,
) -> dict:
    """Build the IDTA 02006 SimulationModels submodel JSON for BaSyx V2.

    *extra_info* may contain any of the following optional provider-supplied keys:
    ``description`` (shown as ``Summary``), ``license`` (SPDX or free text),
    ``documentationUrl``, ``contactEmail``.

    *fmu_path* is the filesystem path to the ``.fmu`` binary; when supplied a
    SHA-256 digest is computed and embedded in the ``ModelFile`` element.
    """
    submodel_id = _submodel_id_for_fmu(lab_id)

    # Summary (MultiLanguageProperty per IDTA 02006) — extra_info takes precedence over FMU
    _description = (extra_info or {}).get("description", "").strip() or metadata.get("description", "").strip()
    sim_model_elements: list[dict] = []
    if _description:
        sim_model_elements.append({
            "idShort": "Summary",
            "modelType": "MultiLanguageProperty",
            "value": [{"language": "en", "text": _description}],
        })

    sim_model_elements += [
        {"idShort": "ModelName", "modelType": "Property", "valueType": "xs:string", "value": metadata.get("modelName", "Unknown")},
        {"idShort": "FmiVersion", "modelType": "Property", "valueType": "xs:string", "value": metadata.get("fmiVersion", "2.0")},
        {"idShort": "SimulationType", "modelType": "Property", "valueType": "xs:string", "value": metadata.get("simulationType", "Unknown")},
        {"idShort": "SupportsCoSimulation", "modelType": "Property", "valueType": "xs:boolean", "value": str(metadata.get("supportsCoSimulation", False)).lower()},
        {"idShort": "SupportsModelExchange", "modelType": "Property", "valueType": "xs:boolean", "value": str(metadata.get("supportsModelExchange", False)).lower()},
        {"idShort": "DefaultStartTime", "modelType": "Property", "valueType": "xs:double", "value": str(metadata.get("defaultStartTime", 0.0))},
        {"idShort": "DefaultStopTime", "modelType": "Property", "valueType": "xs:double", "value": str(metadata.get("defaultStopTime", 1.0))},
        {"idShort": "DefaultStepSize", "modelType": "Property", "valueType": "xs:double", "value": str(metadata.get("defaultStepSize", 0.01))},
        {"idShort": "AccessKey", "modelType": "Property", "valueType": "xs:string", "value": access_key},
        {"idShort": "SyncTimestamp", "modelType": "Property", "valueType": "xs:dateTime", "value": datetime.now(timezone.utc).isoformat()},
    ]

    # ModelFile (File element per IDTA 02006) — best-effort SHA-256 when fmu_path is available
    _fmu_sha256 = ""
    if fmu_path is not None:
        try:
            _fmu_sha256 = hashlib.sha256(Path(fmu_path).read_bytes()).hexdigest()
        except OSError:
            # The digest is optional metadata; retain the AAS without it.
            pass
    _model_file: dict = {
        "idShort": "ModelFile",
        "modelType": "File",
        "contentType": "application/octet-stream",
        "value": f"/fmu-data/{access_key}",
    }
    if _fmu_sha256:
        _model_file["extensions"] = [{"name": "sha256", "valueType": "xs:string", "value": _fmu_sha256}]
    sim_model_elements.append(_model_file)

    # FMU-embedded fields passed through transparently (no form input needed)
    for idshort, key in (
        ("Author", "author"),
        ("Version", "version"),
    ):
        value = metadata.get(key, "").strip()
        if value:
            sim_model_elements.append(
                {"idShort": idshort, "modelType": "Property", "valueType": "xs:string", "value": value}
            )
    # SimulationToolSupport — IDTA 02006 SMC structure replacing flat GenerationTool property
    _gen_tool = metadata.get("generationTool", "").strip()
    if _gen_tool:
        sim_model_elements.append({
            "idShort": "SimulationToolSupport",
            "modelType": "SubmodelElementCollection",
            "value": [
                {
                    "idShort": "SimulationTool_0",
                    "modelType": "SubmodelElementCollection",
                    "value": [
                        {"idShort": "SimulationToolName", "modelType": "Property", "valueType": "xs:string", "value": _gen_tool},
                        {"idShort": "SupportedFMIVersion", "modelType": "Property", "valueType": "xs:string", "value": metadata.get("fmiVersion", "")},
                    ],
                }
            ],
        })
    tolerance = metadata.get("defaultTolerance")
    if tolerance is not None:
        sim_model_elements.append(
            {"idShort": "Tolerance", "modelType": "Property", "valueType": "xs:double", "value": str(tolerance)}
        )

    # CoSimulation/ModelExchange capability flags (machine-readable, no user input needed)
    capabilities = metadata.get("capabilities", {})
    if capabilities:
        cap_elements = []
        for idshort, key in (
            ("CanGetAndSetFMUstate", "canGetAndSetFMUstate"),
            ("CanSerializeFMUstate", "canSerializeFMUstate"),
            ("CanHandleVariableCommunicationStepSize", "canHandleVariableCommunicationStepSize"),
            ("ProvidesDirectionalDerivative", "providesDirectionalDerivative"),
            ("ProvidesAdjointDerivatives", "providesAdjointDerivatives"),
        ):
            val = capabilities.get(key)
            if val is not None:
                cap_elements.append(
                    {"idShort": idshort, "modelType": "Property", "valueType": "xs:boolean", "value": str(val).lower()}
                )
        fixed_step = capabilities.get("fixedInternalStepSize")
        if fixed_step is not None:
            cap_elements.append(
                {"idShort": "FixedInternalStepSize", "modelType": "Property", "valueType": "xs:double", "value": str(fixed_step)}
            )
        if cap_elements:
            sim_model_elements.append({
                "idShort": "Capabilities",
                "modelType": "SubmodelElementCollection",
                "value": cap_elements,
            })

    # Provider-supplied metadata (may be auto-filled from FMU or entered manually)
    if extra_info:
        for idshort, key in (
            ("License", "license"),
            ("DocumentationUrl", "documentationUrl"),
            ("ContactEmail", "contactEmail"),
        ):
            value = extra_info.get(key, "").strip()
            if value:
                sim_model_elements.append(
                    {"idShort": idshort, "modelType": "Property", "valueType": "xs:string", "value": value}
                )

    ports = build_simulation_ports(metadata.get("modelVariables", []))
    if ports:
        sim_model_elements.append({
            "idShort": "Ports",
            "modelType": "SubmodelElementCollection",
            "value": ports,
        })

    submodel = {
        "id": submodel_id,
        "idShort": "SimulationModels",
        "semanticId": {
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": _SEMANTIC_ID_IDTA_02006}],
        },
        "modelType": "Submodel",
        "submodelElements": [
            {
                "idShort": "SimulationModel",
                "semanticId": {
                    "type": "ExternalReference",
                    "keys": [{"type": "GlobalReference", "value": _SEMANTIC_ID_SIMULATION_MODEL}],
                },
                "modelType": "SubmodelElementCollection",
                "value": sim_model_elements,
            }
        ],
    }
    return submodel


def build_unit_definitions_submodel(lab_id: str, unit_defs: list) -> dict:
    """Build a UnitDefinitions submodel from FMU unit definitions.

    Each unit in *unit_defs* becomes a ``SubmodelElementCollection`` whose
    ``idShort`` is sanitized from the unit name.  Optional ``baseUnit`` and
    ``displayUnits`` keys are rendered as nested collections with their SI
    exponent properties and conversion factors.
    """
    elements: list[dict] = []
    seen_idshorts: set[str] = set()
    for unit in unit_defs:
        base_idshort = _sanitize_idshort(unit["name"])
        idshort = base_idshort
        idx = 1
        while idshort in seen_idshorts:
            idshort = f"{base_idshort}_{idx}"
            idx += 1
        seen_idshorts.add(idshort)

        unit_props: list[dict] = [
            {"idShort": "Name", "modelType": "Property", "valueType": "xs:string", "value": unit["name"]},
        ]

        if "baseUnit" in unit:
            bu = unit["baseUnit"]
            bu_elements: list[dict] = []
            for exp in ("kg", "m", "s", "A", "K", "mol", "cd", "rad"):
                if exp in bu:
                    bu_elements.append(
                        {"idShort": exp, "modelType": "Property", "valueType": "xs:int", "value": str(bu[exp])}
                    )
            if "factor" in bu:
                bu_elements.append(
                    {"idShort": "Factor", "modelType": "Property", "valueType": "xs:double", "value": str(bu["factor"])}
                )
            if "offset" in bu:
                bu_elements.append(
                    {"idShort": "Offset", "modelType": "Property", "valueType": "xs:double", "value": str(bu["offset"])}
                )
            if bu_elements:
                unit_props.append(
                    {"idShort": "BaseUnit", "modelType": "SubmodelElementCollection", "value": bu_elements}
                )

        if "displayUnits" in unit:
            du_elements: list[dict] = []
            seen_du: set[str] = set()
            for du in unit["displayUnits"]:
                du_idshort = _sanitize_idshort(du["name"])
                di = 1
                while du_idshort in seen_du:
                    du_idshort = f"{_sanitize_idshort(du['name'])}_{di}"
                    di += 1
                seen_du.add(du_idshort)
                du_props: list[dict] = [
                    {"idShort": "Name", "modelType": "Property", "valueType": "xs:string", "value": du["name"]},
                ]
                if "factor" in du:
                    du_props.append(
                        {"idShort": "Factor", "modelType": "Property", "valueType": "xs:double", "value": str(du["factor"])}
                    )
                if "offset" in du:
                    du_props.append(
                        {"idShort": "Offset", "modelType": "Property", "valueType": "xs:double", "value": str(du["offset"])}
                    )
                du_elements.append(
                    {"idShort": du_idshort, "modelType": "SubmodelElementCollection", "value": du_props}
                )
            if du_elements:
                unit_props.append(
                    {"idShort": "DisplayUnits", "modelType": "SubmodelElementCollection", "value": du_elements}
                )

        elements.append({"idShort": idshort, "modelType": "SubmodelElementCollection", "value": unit_props})

    return {
        "id": _unit_submodel_id_for_lab(lab_id),
        "idShort": "UnitDefinitions",
        "semanticId": {
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": "https://decentralabs.io/aas/UnitDefinitions/1/0"}],
        },
        "modelType": "Submodel",
        "submodelElements": elements,
    }


def build_aas_shell(
    lab_id: str,
    access_key: str,
    metadata: dict,
    extra_info: Optional[dict] = None,
    extra_submodel_ids: list = (),
) -> dict:
    """Build the AAS shell JSON for BaSyx V2.

    *extra_info* may contain ``description`` (str) for a human-readable
    description of the asset, surfaced as the AAS shell ``description`` field.
    *extra_submodel_ids* lists the IDs of additional submodels (e.g.
    UnitDefinitions) that should appear in the shell's submodel references.
    """
    aas_id = _aas_id_for_lab(lab_id)
    all_sm_ids = [_submodel_id_for_fmu(lab_id), *extra_submodel_ids]

    shell = {
        "id": aas_id,
        "idShort": f"DecentraLabs_Lab_{lab_id}",
        "modelType": "AssetAdministrationShell",
        "assetInformation": {
            "assetKind": "Instance",
            "globalAssetId": aas_id,
            "assetType": "FMU",
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


async def sync_fmu_to_basyx(
    lab_id: str,
    access_key: str,
    metadata: dict,
    aasx_bytes: Optional[bytes] = None,
    extra_info: Optional[dict] = None,
    fmu_path: Optional[Path] = None,
    unit_definitions: list = (),
) -> dict:
    """
    Create or update the AAS shell and SimulationModels submodel in BaSyx.

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

    result: dict = {"aasId": aas_id, "submodelId": submodel_id, "created": False, "updated": False}

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

                # Build unit definitions submodel first (its ID is needed for the shell)
                _unit_sm_id: Optional[str] = None
                _unit_sm_payload: Optional[dict] = None
                if unit_definitions:
                    _unit_sm_id = _unit_submodel_id_for_lab(lab_id)
                    _unit_sm_payload = build_unit_definitions_submodel(lab_id, list(unit_definitions))
                _extra_sm_ids: list = [_unit_sm_id] if _unit_sm_id else []

                shell_payload = build_aas_shell(lab_id, access_key, metadata, extra_info, extra_submodel_ids=_extra_sm_ids)
                submodel_payload = build_simulation_submodel(lab_id, access_key, metadata, extra_info, fmu_path=fmu_path)

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
                    logger.info("Created submodel %s for lab %s", submodel_id, lab_id)
                elif sm_resp.status_code in (200, 204):
                    result["updated"] = True
                    logger.info("Updated submodel %s for lab %s", submodel_id, lab_id)
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
                            logger.info("Created submodel %s via POST for lab %s", submodel_id, lab_id)
                        else:
                            logger.error("Failed to create submodel %s: %s %s", submodel_id, sm_post.status_code, sm_post.text[:500])
                            result["error"] = f"submodel creation failed: {sm_post.status_code}"
                            return result
                    else:
                        logger.error("Failed to PUT submodel %s: %s %s", submodel_id, sm_resp.status_code, sm_resp.text[:500])
                        result["error"] = f"submodel sync failed: {sm_resp.status_code}"
                        return result

                # --- UnitDefinitions submodel: PUT when FMU declares physical units ---
                if _unit_sm_payload and _unit_sm_id:
                    _usm_enc = _encode_id(_unit_sm_id)
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", _usm_enc):
                        raise ValueError("AAS unit definitions resource ID is invalid")
                    _usm_resp = await client.put(
                        f"/submodels/{_usm_enc}",
                        json=_unit_sm_payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if _usm_resp.status_code in (200, 201, 204):
                        logger.info("UnitDefinitions submodel synced for lab %s", lab_id)
                    elif _usm_resp.status_code == 404:
                        _usm_post = await client.post(
                            "/submodels", json=_unit_sm_payload,
                            headers={"Content-Type": "application/json"},
                        )
                        if _usm_post.status_code in (200, 201):
                            logger.info("UnitDefinitions submodel created via POST for lab %s", lab_id)
                        else:
                            logger.warning(
                                "Failed to create UnitDefinitions submodel for lab %s: %s",
                                lab_id, _usm_post.status_code,
                            )
                    else:
                        logger.warning("Failed to PUT UnitDefinitions submodel for lab %s", str(lab_id).replace("\r", "\\r").replace("\n", "\\n"))

                # --- Shell: PUT (create or replace) ---
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", aas_id_encoded):
                    raise ValueError("AAS shell resource ID is invalid")
                shell_resp = await client.put(
                    f"/shells/{aas_id_encoded}",
                    json=shell_payload,
                    headers={"Content-Type": "application/json"},
                )
                if shell_resp.status_code == 201:
                    logger.info("Created AAS shell %s for lab %s", aas_id, lab_id)
                elif shell_resp.status_code in (200, 204):
                    logger.info("Updated AAS shell %s for lab %s", aas_id, lab_id)
                else:
                    if shell_resp.status_code == 404:
                        shell_post = await client.post(
                            "/shells",
                            json=shell_payload,
                            headers={"Content-Type": "application/json"},
                        )
                        if shell_post.status_code in (200, 201):
                            logger.info("Created AAS shell %s via POST for lab %s", aas_id, lab_id)
                        else:
                            logger.error("Failed to create shell %s: %s %s", aas_id, shell_post.status_code, shell_post.text[:500])
                            result["error"] = f"shell creation failed: {shell_post.status_code}"
                            return result
                    else:
                        logger.error("Failed to PUT shell %s: %s %s", aas_id, shell_resp.status_code, shell_resp.text[:500])
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
