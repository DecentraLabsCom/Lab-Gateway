"""
AAS shell and submodel generator for physical laboratory resources.

Generates BaSyx V2-compatible JSON payloads from host config and heartbeat data.
Uses a simplified Nameplate submodel for lab identity and a TechnicalData submodel
for current operational status derived from the Lab Station heartbeat.
"""

import base64
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import requests

logger = logging.getLogger("ops-worker.aas")

# Empty default: if not configured (e.g. Lite mode gateways without --profile aas),
# sync_lab_to_basyx returns a disabled result instead of attempting a connection.
BASYX_AAS_URL = os.getenv("BASYX_AAS_URL", "")
AAS_ALLOWED_HOSTS = os.getenv("AAS_ALLOWED_HOSTS", "")
AAS_SERVICE_TOKEN = os.getenv("AAS_SERVICE_TOKEN", "")
AAS_SERVICE_TOKEN_HEADER = os.getenv("AAS_SERVICE_TOKEN_HEADER", "Authorization")
_BUNDLED_AAS_URL = "http://basyx-aas-server:8081"

_BASYX_TIMEOUT = int(os.getenv("BASYX_AAS_TIMEOUT", "15"))
_AAS_LAB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def _aas_request_headers() -> Dict[str, str]:
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


def build_physical_aas_shell(lab_id: str, host: Dict[str, Any]) -> Dict[str, Any]:
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
    if not re.fullmatch(r"/(?:shells|submodels)/[A-Za-z0-9_-]{1,1024}", put_path) or post_path not in ("/shells", "/submodels"):
        raise ValueError("AAS resource path is invalid")

    endpoint = str(url_base).rstrip("/")
    if endpoint == _BUNDLED_AAS_URL:
        pass
    else:
        parsed = urlsplit(endpoint)
        allowed_hosts = {
            value.strip().lower()
            for value in AAS_ALLOWED_HOSTS.split(",")
            if value.strip()
        }
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.hostname.lower() not in allowed_hosts
        ):
            raise ValueError("external AAS endpoint is not allowlisted")

    resp = session.put(f"{endpoint}{put_path}", json=payload, timeout=_BASYX_TIMEOUT)
    if resp.status_code in (200, 201, 204):
        return {"status": resp.status_code, "created": resp.status_code == 201}
    if resp.status_code == 404:
        resp2 = session.post(f"{endpoint}{post_path}", json=payload, timeout=_BASYX_TIMEOUT)
        if resp2.status_code in (200, 201):
            return {"status": resp2.status_code, "created": True}
        logger.warning("BaSyx POST failed with status=%s", resp2.status_code)
        return {"error": f"POST failed: {resp2.status_code}"}
    logger.warning("BaSyx PUT failed with status=%s", resp.status_code)
    return {"error": f"PUT failed: {resp.status_code}"}


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
    try:
        lab_id = _validate_lab_id(lab_id)
    except ValueError:
        return {"error": "AAS lab ID rejected", "created": False, "updated": False}

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

    shell_payload = build_physical_aas_shell(lab_id, host)
    nameplate_payload = build_nameplate_submodel(lab_id, host)
    technical_payload = build_technical_data_submodel(lab_id, host, heartbeat)

    aas_id_enc = _encode_id(aas_id)
    np_id_enc = _encode_id(nameplate_id)
    td_id_enc = _encode_id(technical_id)

    try:
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json", **_aas_request_headers()})

        # --- Nameplate submodel ---
        np_result = _put_or_post(session, BASYX_AAS_URL, f"/submodels/{np_id_enc}", "/submodels", nameplate_payload)
        if "error" in np_result:
            logger.error("Failed to sync Nameplate submodel")
            result["error"] = "nameplate sync failed"
            return result
        if np_result.get("created"):
            result["created"] = True
        else:
            result["updated"] = True
        logger.info("Nameplate submodel synced (status=%s)", np_result.get("status"))

        # --- TechnicalData submodel ---
        td_result = _put_or_post(session, BASYX_AAS_URL, f"/submodels/{td_id_enc}", "/submodels", technical_payload)
        if "error" in td_result:
            logger.error("Failed to sync TechnicalData submodel")
            result["error"] = "technicalData sync failed"
            return result
        logger.info("TechnicalData submodel synced (status=%s)", td_result.get("status"))

        # --- AAS Shell ---
        shell_result = _put_or_post(session, BASYX_AAS_URL, f"/shells/{aas_id_enc}", "/shells", shell_payload)
        if "error" in shell_result:
            logger.error("Failed to sync AAS shell")
            result["error"] = "shell sync failed"
            return result
        logger.info("AAS shell synced (status=%s)", shell_result.get("status"))

    except requests.exceptions.ConnectionError as exc:
        logger.warning("BaSyx unreachable at %s: %s", BASYX_AAS_URL, exc)
        result["error"] = "BaSyx unreachable"
        return result
    except requests.exceptions.Timeout as exc:
        logger.warning("BaSyx timeout at %s: %s", BASYX_AAS_URL, exc)
        result["error"] = "BaSyx timeout"
        return result
    except ValueError as exc:
        logger.error("AAS endpoint policy rejected %s: %s", BASYX_AAS_URL, exc)
        result["error"] = "AAS endpoint policy rejected"
        return result

    result["synced"] = True
    return result
