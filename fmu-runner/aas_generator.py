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
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger("fmu-runner.aas")

# Empty default: if not configured (e.g. Lite mode gateways without --profile aas),
# sync_fmu_to_basyx returns a disabled result instead of attempting a connection.
BASYX_AAS_URL = os.getenv("BASYX_AAS_URL", "")
FMU_DATA_PATH = os.getenv("FMU_DATA_PATH", "/app/fmu-data")

_SEMANTIC_ID_IDTA_02006 = "https://admin-shell.io/idta/SimulationModels/SimulationModels/1/0"
_SEMANTIC_ID_SIMULATION_MODEL = "https://admin-shell.io/idta/SimulationModels/SimulationModel/1/0"
_SEMANTIC_ID_SIMULATION_MODEL_PORT = "https://admin-shell.io/idta/SimulationModels/PortsInformation/Port/1/0"


def _aas_id_for_lab(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}"


def _submodel_id_for_fmu(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:simulationModels"


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
                {"idShort": "PortDirection", "modelType": "Property", "valueType": "xs:string", "value": _causality_to_port_type(causality)},
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

        ports.append(port_element)
    return ports


def build_simulation_submodel(lab_id: str, access_key: str, metadata: dict) -> dict:
    """Build the IDTA 02006 SimulationModels submodel JSON for BaSyx V2."""
    submodel_id = _submodel_id_for_fmu(lab_id)

    sim_model_elements = [
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


def build_aas_shell(lab_id: str, access_key: str, metadata: dict) -> dict:
    """Build the AAS shell JSON for BaSyx V2."""
    aas_id = _aas_id_for_lab(lab_id)
    submodel_id = _submodel_id_for_fmu(lab_id)

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
            {
                "type": "ModelReference",
                "keys": [{"type": "Submodel", "value": submodel_id}],
            }
        ],
    }
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
) -> dict:
    """
    Create or update the AAS shell and SimulationModels submodel in BaSyx.

    If *aasx_bytes* is provided the package is parsed and every shell /
    submodel it contains is uploaded to BaSyx via the standard JSON REST
    API (PUT, fallback POST).  When *aasx_bytes* is ``None`` the shell and
    submodel are auto-generated from *metadata*.

    Returns a summary dict with ids and status.
    """
    aas_id = _aas_id_for_lab(lab_id)
    submodel_id = _submodel_id_for_fmu(lab_id)

    result: dict = {"aasId": aas_id, "submodelId": submodel_id, "created": False, "updated": False}

    if not BASYX_AAS_URL:
        logger.info("BASYX_AAS_URL not configured — AAS sync disabled (Lite or non-AAS gateway).")
        result["disabled"] = True
        return result

    try:
        async with httpx.AsyncClient(base_url=BASYX_AAS_URL, timeout=15.0) as client:
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
                shell_payload = build_aas_shell(lab_id, access_key, metadata)
                submodel_payload = build_simulation_submodel(lab_id, access_key, metadata)

                # --- Submodel: PUT (create or replace) ---
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

                # --- Shell: PUT (create or replace) ---
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
        logger.warning("BaSyx unreachable at %s: %s", BASYX_AAS_URL, exc)
        result["error"] = f"BaSyx unreachable: {exc}"
        return result

    result["synced"] = True
    return result
