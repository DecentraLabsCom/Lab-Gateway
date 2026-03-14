"""
AAS shell and submodel generator for physical laboratory resources.

Generates BaSyx V2-compatible JSON payloads from host config and heartbeat data.
Uses a simplified Nameplate submodel for lab identity and a TechnicalData submodel
for current operational status derived from the Lab Station heartbeat.
"""

import base64
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("ops-worker.aas")

# Empty default: if not configured (e.g. Lite mode gateways without --profile aas),
# sync_lab_to_basyx returns a disabled result instead of attempting a connection.
BASYX_AAS_URL = os.getenv("BASYX_AAS_URL", "")

_BASYX_TIMEOUT = int(os.getenv("BASYX_AAS_TIMEOUT", "15"))


def _aas_id_for_lab(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}"


def _submodel_id_nameplate(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:nameplate"


def _submodel_id_technical(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:technicalData"


def _encode_id(raw_id: str) -> str:
    """Base64url-encode an AAS/submodel ID for BaSyx V2 REST paths."""
    return base64.urlsafe_b64encode(raw_id.encode()).decode().rstrip("=")


def _prop(id_short: str, value_type: str, value: Any) -> Dict[str, Any]:
    return {
        "idShort": id_short,
        "modelType": "Property",
        "valueType": value_type,
        "value": str(value) if value is not None else "",
    }


def build_nameplate_submodel(lab_id: str, host: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a simplified Nameplate submodel for a physical lab host.

    Covers the core identity fields: lab ID, host name, address type, and
    the mapping from host → lab IDs served by this station.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    elements = [
        _prop("LabId", "xs:string", lab_id),
        _prop("HostName", "xs:string", host.get("name", "")),
        _prop("LabType", "xs:string", "PhysicalLab"),
        _prop("NetworkAddress", "xs:string", host.get("address", "")),
        _prop("SyncTimestamp", "xs:string", now_iso),
    ]

    mac = host.get("mac")
    if mac:
        elements.append(_prop("MacAddress", "xs:string", mac))

    labs = host.get("labs", [])
    if labs:
        elements.append(_prop("MappedLabIds", "xs:string", ", ".join(str(lid) for lid in labs)))

    return {
        "id": _submodel_id_nameplate(lab_id),
        "idShort": "Nameplate",
        "modelType": "Submodel",
        "semanticId": {
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": "https://admin-shell.io/zvei/nameplate/2/0/Nameplate"}],
        },
        "submodelElements": elements,
    }


def build_technical_data_submodel(
    lab_id: str,
    host: Dict[str, Any],
    heartbeat: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a TechnicalData submodel from heartbeat operational status.

    If no heartbeat is provided (lab not yet polled), status fields are empty.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    hb = heartbeat or {}

    summary = hb.get("summary", {})
    status = hb.get("status", {})
    operations = hb.get("operations", {})

    ready = summary.get("ready")
    local_mode = status.get("localModeEnabled")
    local_session = status.get("localSessionActive")
    hb_timestamp = hb.get("timestamp", "")

    last_power = operations.get("lastPowerAction") or {}
    last_power_ts = last_power.get("timestamp", "")
    last_power_mode = last_power.get("mode", "")

    last_logoff = operations.get("lastForcedLogoff") or {}
    last_logoff_ts = last_logoff.get("timestamp", "")
    last_logoff_user = last_logoff.get("user", "")

    def bool_str(val: Any) -> str:
        if val is None:
            return ""
        return "true" if val else "false"

    elements = [
        _prop("LabStatus", "xs:string", "Ready" if ready else ("NotReady" if ready is False else "")),
        _prop("ReadyFlag", "xs:boolean", bool_str(ready)),
        _prop("LocalModeEnabled", "xs:boolean", bool_str(local_mode)),
        _prop("LocalSessionActive", "xs:boolean", bool_str(local_session)),
        _prop("LastHeartbeatTimestamp", "xs:string", hb_timestamp),
        _prop("LastPowerActionTimestamp", "xs:string", last_power_ts),
        _prop("LastPowerActionMode", "xs:string", last_power_mode),
        _prop("LastForcedLogoffTimestamp", "xs:string", last_logoff_ts),
        _prop("LastForcedLogoffUser", "xs:string", last_logoff_user),
        _prop("SyncTimestamp", "xs:string", now_iso),
    ]

    return {
        "id": _submodel_id_technical(lab_id),
        "idShort": "TechnicalData",
        "modelType": "Submodel",
        "semanticId": {
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": "https://admin-shell.io/ZVEI/TechnicalData/Submodel/1/2"}],
        },
        "submodelElements": elements,
    }


def build_aas_shell(lab_id: str, host: Dict[str, Any]) -> Dict[str, Any]:
    """Build the AAS shell for a physical lab resource."""
    aas_id = _aas_id_for_lab(lab_id)
    nameplate_id = _submodel_id_nameplate(lab_id)
    technical_id = _submodel_id_technical(lab_id)
    host_name = host.get("name", lab_id)
    return {
        "id": aas_id,
        "idShort": f"DecentraLabs_Lab_{lab_id}",
        "modelType": "AssetAdministrationShell",
        "assetInformation": {
            "assetKind": "Instance",
            "globalAssetId": aas_id,
            "assetType": "PhysicalLab",
        },
        "description": [
            {"language": "en", "text": f"Physical lab resource '{host_name}' (labId={lab_id})"},
        ],
        "submodels": [
            {"type": "ModelReference", "keys": [{"type": "Submodel", "value": nameplate_id}]},
            {"type": "ModelReference", "keys": [{"type": "Submodel", "value": technical_id}]},
        ],
    }


def _put_or_post(session: requests.Session, url_base: str, put_path: str, post_path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """PUT to create-or-replace; fall back to POST if server returns 404."""
    resp = session.put(f"{url_base}{put_path}", json=payload, timeout=_BASYX_TIMEOUT)
    if resp.status_code in (200, 201, 204):
        return {"status": resp.status_code, "created": resp.status_code == 201}
    if resp.status_code == 404:
        resp2 = session.post(f"{url_base}{post_path}", json=payload, timeout=_BASYX_TIMEOUT)
        if resp2.status_code in (200, 201):
            return {"status": resp2.status_code, "created": True}
        return {"error": f"POST failed: {resp2.status_code}", "body": resp2.text[:500]}
    return {"error": f"PUT failed: {resp.status_code}", "body": resp.text[:500]}


def sync_lab_to_basyx(
    lab_id: str,
    host: Dict[str, Any],
    heartbeat: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Sync (create or update) the AAS shell and submodels for a physical lab resource
    into the BaSyx server.

    Returns a summary dict:
    - {"disabled": True}  if BASYX_AAS_URL is not configured (Lite Gateway)
    - {"error": "..."}    if BaSyx is unreachable or returns an error
    - {"synced": True, ...} on success
    """
    aas_id = _aas_id_for_lab(lab_id)
    nameplate_id = _submodel_id_nameplate(lab_id)
    technical_id = _submodel_id_technical(lab_id)

    result: Dict[str, Any] = {
        "aasId": aas_id,
        "nameplateSubmodelId": nameplate_id,
        "technicalDataSubmodelId": technical_id,
        "created": False,
        "updated": False,
    }

    if not BASYX_AAS_URL:
        logger.info("BASYX_AAS_URL not configured — AAS sync disabled (Lite or non-AAS gateway).")
        result["disabled"] = True
        return result

    shell_payload = build_aas_shell(lab_id, host)
    nameplate_payload = build_nameplate_submodel(lab_id, host)
    technical_payload = build_technical_data_submodel(lab_id, host, heartbeat)

    aas_id_enc = _encode_id(aas_id)
    np_id_enc = _encode_id(nameplate_id)
    td_id_enc = _encode_id(technical_id)

    try:
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})

        # --- Nameplate submodel ---
        np_result = _put_or_post(session, BASYX_AAS_URL, f"/submodels/{np_id_enc}", "/submodels", nameplate_payload)
        if "error" in np_result:
            logger.error("Failed to sync Nameplate submodel for lab %s: %s", lab_id, np_result["error"])
            result["error"] = f"nameplate sync failed: {np_result['error']}"
            return result
        if np_result.get("created"):
            result["created"] = True
        else:
            result["updated"] = True
        logger.info("Nameplate submodel synced for lab %s (status=%s)", lab_id, np_result.get("status"))

        # --- TechnicalData submodel ---
        td_result = _put_or_post(session, BASYX_AAS_URL, f"/submodels/{td_id_enc}", "/submodels", technical_payload)
        if "error" in td_result:
            logger.error("Failed to sync TechnicalData submodel for lab %s: %s", lab_id, td_result["error"])
            result["error"] = f"technicalData sync failed: {td_result['error']}"
            return result
        logger.info("TechnicalData submodel synced for lab %s (status=%s)", lab_id, td_result.get("status"))

        # --- AAS Shell ---
        shell_result = _put_or_post(session, BASYX_AAS_URL, f"/shells/{aas_id_enc}", "/shells", shell_payload)
        if "error" in shell_result:
            logger.error("Failed to sync AAS shell for lab %s: %s", lab_id, shell_result["error"])
            result["error"] = f"shell sync failed: {shell_result['error']}"
            return result
        logger.info("AAS shell synced for lab %s (status=%s)", lab_id, shell_result.get("status"))

    except requests.exceptions.ConnectionError as exc:
        logger.warning("BaSyx unreachable at %s: %s", BASYX_AAS_URL, exc)
        result["error"] = f"BaSyx unreachable: {exc}"
        return result
    except requests.exceptions.Timeout as exc:
        logger.warning("BaSyx timeout at %s: %s", BASYX_AAS_URL, exc)
        result["error"] = f"BaSyx timeout: {exc}"
        return result

    result["synced"] = True
    return result
