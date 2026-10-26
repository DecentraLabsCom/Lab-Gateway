"""Read, validate, and synchronize AAS Part 4 access-control submodels."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from typing import Any, Optional

import httpx

from aas_model_builders import (
    _SEMANTIC_ID_SIMULATION_ACCESS_CONTROL,
    _encode_id,
    _submodel_id_for_access_control,
    build_simulation_access_control_submodel,
)

logger = logging.getLogger("fmu-runner.aas")
_AAS_ENCODED_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,1024}")


def _decode_part4_access_rules_blob(element: Any) -> dict[str, Any] | None:
    if (
        not isinstance(element, dict)
        or element.get("modelType") != "Blob"
        or str(element.get("contentType") or "").lower() != "application/json"
    ):
        return None
    encoded = element.get("value")
    if not isinstance(encoded, str) or len(encoded) > 2 * 1_048_576:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 1_048_576:
            return None
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and set(payload) == {"AllAccessPermissionRules"} else None

def _is_simulation_access_control_submodel(submodel: Any) -> bool:
    if not isinstance(submodel, dict):
        return False
    if submodel.get("idShort") == "SimulationAccessControl":
        return True
    semantic_id = submodel.get("semanticId")
    if isinstance(semantic_id, dict):
        keys = semantic_id.get("keys")
        if isinstance(keys, list) and any(
            isinstance(key, dict) and key.get("value") == _SEMANTIC_ID_SIMULATION_ACCESS_CONTROL
            for key in keys
        ):
            return True
    elements = submodel.get("submodelElements")
    return isinstance(elements, list) and any(
        _decode_part4_access_rules_blob(element) is not None
        for element in elements
    )

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

async def _sync_simulation_access_control(
    client: httpx.AsyncClient,
    lab_id: str,
    metadata: dict,
    *,
    simulation_model_submodel_id: str | None = None,
    force_regenerate: bool = False,
) -> dict[str, Any]:
    """Upsert generated rules without overwriting provider-edited rules."""
    submodel_id = _submodel_id_for_access_control(lab_id)
    encoded_id = _encode_id(submodel_id)
    if _AAS_ENCODED_ID_RE.fullmatch(encoded_id) is None:
        return {"error": "AAS access control resource ID is invalid"}

    payload = build_simulation_access_control_submodel(
        lab_id,
        metadata,
        simulation_model_submodel_id=simulation_model_submodel_id,
    )
    current = await client.get(f"/submodels/{encoded_id}")
    if current.status_code == 200:
        try:
            existing = current.json()
        except (TypeError, ValueError):
            return {"error": "AAS access control resource is invalid"}
        if not isinstance(existing, dict):
            return {"error": "AAS access control resource is invalid"}
        old_generated_digest = _find_property_value(existing, "GeneratedPolicyDigest")
        old_interface_digest = _find_property_value(existing, "InterfaceDigest")
        old_blob = next((
            element for element in existing.get("submodelElements", [])
            if isinstance(element, dict)
            and element.get("idShort") == "AllAccessPermissionRules"
            and element.get("modelType") == "Blob"
        ), None)
        blob_digest = None
        if isinstance(old_blob, dict) and isinstance(old_blob.get("value"), str):
            try:
                blob_digest = hashlib.sha256(base64.b64decode(old_blob["value"], validate=True)).hexdigest()
            except (ValueError, TypeError):
                blob_digest = "invalid"
        if not force_regenerate and (not old_generated_digest or blob_digest != old_generated_digest):
            # A changed or externally authored policy is provider-owned. Its
            # old interface digest intentionally remains, making it stale and
            # unusable after an incompatible FMU update until reviewed.
            payload = existing
            new_digest = _find_property_value(
                build_simulation_access_control_submodel(
                    lab_id,
                    metadata,
                    simulation_model_submodel_id=simulation_model_submodel_id,
                ),
                "InterfaceDigest",
            )
            return_flags = {
                "accessPolicyPreserved": True,
                "accessPolicyStale": old_interface_digest != new_digest,
            }
        else:
            return_flags = {"accessPolicyRegenerated": True} if force_regenerate else {}
    elif current.status_code == 404:
        return_flags = {}
    else:
        return {"error": f"access policy lookup failed: {current.status_code}"}

    response = await client.put(
        f"/submodels/{encoded_id}",
        json=payload,
        headers={"Content-Type": "application/json"},
    )
    if response.status_code in (200, 201, 204):
        return {
            "created": response.status_code == 201,
            "updated": response.status_code != 201,
            **return_flags,
        }
    if response.status_code == 404:
        response = await client.post(
            "/submodels",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code in (200, 201):
            return {"created": True, **return_flags}
    return {"error": f"access policy sync failed: {response.status_code}"}
