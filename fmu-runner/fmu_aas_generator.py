"""Coordinate FMU AAS payload generation and BaSyx synchronization."""

import base64
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import urlsplit

import httpx
from aas_model_builders import (
    _AAS_LAB_ID_RE,
    _FMI_VARIABLE_METADATA_EXTENSION,
    _IDSHORT_UNSAFE_RE,
    _MAX_FMI_VARIABLE_METADATA_BYTES,
    _SEMANTIC_ID_ACCESS_GENERATED_DIGEST,
    _SEMANTIC_ID_ACCESS_INTERFACE_DIGEST,
    _SEMANTIC_ID_ARBITRARY,
    _SEMANTIC_ID_ASSET_INTERFACES,
    _SEMANTIC_ID_CAPABILITY_DESCRIPTION,
    _SEMANTIC_ID_CONTACT_INFORMATION,
    _SEMANTIC_ID_FMI_LS_RELATED_RESOURCES,
    _SEMANTIC_ID_HANDOVER_DOCUMENTATION,
    _SEMANTIC_ID_SIMULATION_ACCESS_CONTROL,
    _SEMANTIC_ID_SIMULATION_MODEL,
    _SEMANTIC_ID_SIMULATION_MODELS,
    _SEMANTIC_ID_TECHNICAL_DATA,
    _SIMULATION_SEMANTICS,
    _aas_id_for_lab,
    _arbitrary_property,
    _asset_interface_action,
    _causality_to_port_type,
    _documentation_urls,
    _encode_id,
    _fmi_causality_to_idta,
    _fmi_type_to_idta,
    _fmi_variable_metadata_extension,
    _fmu_digest as _model_fmu_digest,
    _non_negative_int,
    _sanitize_idshort,
    _semantic_id,
    _standard_mlp,
    _standard_property,
    _submodel_id_for_access_control,
    _submodel_id_for_contact,
    _submodel_id_for_execution,
    _submodel_id_for_fmi_ls_related_resources,
    _submodel_id_for_fmu,
    _submodel_id_for_handover,
    _submodel_id_for_interfaces,
    _submodel_id_for_technical,
    _validate_lab_id,
    build_aas_shell,
    build_asset_interfaces_description_submodel,
    build_contact_information_submodel,
    build_execution_capabilities_submodel,
    build_fmi_ls_related_resources_submodel,
    build_handover_documentation_submodel,
    build_simulation_access_control_submodel,
    build_simulation_ports,
    build_simulation_submodel as _build_simulation_submodel,
    build_technical_data_submodel,
)
from aas_access_control_sync import (
    _decode_part4_access_rules_blob,
    _find_property_value,
    _is_simulation_access_control_submodel,
    _sync_simulation_access_control,
)
from aasx_import import _parse_aasx_xml_environment, parse_aasx as _parse_aasx_package
from aasx_limits import (
    MAX_AASX_ENVIRONMENT_PART_BYTES,
    MAX_AASX_RELATIONSHIP_PART_BYTES,
    MAX_AASX_UPLOAD_BYTES,
)
from simulation_access_policy import (
    build_part4_access_rules,
    compile_part4_access_rules,
    fmi_interface_digest,
)

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
_AAS_ENCODED_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,1024}")
_AAS_COLLECTIONS = frozenset({"shells", "submodels"})
_AASX_MEDIA_TYPE = "application/asset-administration-shell-package+xml"
_AASX_MEDIA_TYPES = frozenset({
    _AASX_MEDIA_TYPE,
    "application/aasx+xml",
    "application/aas+zip",
})

def _fmu_digest(fmu_path: Path) -> str:
    """Return the digest of the matching FMU under the configured data root."""
    return _model_fmu_digest(fmu_path, FMU_DATA_PATH)

def build_simulation_submodel(
    lab_id: str,
    access_key: str,
    metadata: dict,
    extra_info: Optional[dict] = None,
    *,
    fmu_path: Optional[Path] = None,
) -> dict:
    """Build the simulation model submodel using this module's FMU data root."""
    return _build_simulation_submodel(
        lab_id,
        access_key,
        metadata,
        extra_info,
        fmu_path=fmu_path,
        fmu_data_path=FMU_DATA_PATH,
    )

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

def _aas_resource_path(collection: str, encoded_id: str) -> str:
    """Build a BaSyx resource path from an encoded, single-segment ID."""
    if collection not in _AAS_COLLECTIONS or _AAS_ENCODED_ID_RE.fullmatch(encoded_id) is None:
        raise ValueError("AAS resource path is invalid")
    return f"/{collection}/{encoded_id}"

def _parse_aasx(aasx_bytes: bytes) -> dict:
    """Keep the generator's import surface while delegating AASX parsing."""
    return _parse_aasx_package(
        aasx_bytes,
        max_upload_bytes=MAX_AASX_UPLOAD_BYTES,
        environment_part_bytes=MAX_AASX_ENVIRONMENT_PART_BYTES,
        relationship_part_bytes=MAX_AASX_RELATIONSHIP_PART_BYTES,
    )

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
                params=tuple(params),
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


async def get_handover_visual_assets(lab_id: str) -> list[dict[str, str]]:
    """Read local preview visual assets from the linked AAS handover submodel."""
    normalized_lab_id = str(lab_id or "").strip()
    if _AAS_LAB_ID_RE.fullmatch(normalized_lab_id) is None or not BASYX_AAS_URL:
        return []

    shell_id = f"urn:decentralabs:lab:{normalized_lab_id}"
    handover_id = _submodel_id_for_handover(normalized_lab_id)
    try:
        async with httpx.AsyncClient(
            base_url=BASYX_AAS_URL,
            headers=_aas_request_headers(),
            timeout=8.0,
        ) as client:
            shell_response = await client.get(f"/shells/{_encode_id(shell_id)}")
            if shell_response.status_code == 404:
                return []
            if shell_response.status_code != 200:
                raise RuntimeError("AAS shell could not be read")
            shell = shell_response.json()
            if not isinstance(shell, dict) or shell.get("id") != shell_id:
                raise RuntimeError("AAS shell reference is invalid")
            raw_submodel_ids = shell.get("submodelIds")
            submodel_ids = (
                [value for value in raw_submodel_ids if isinstance(value, str)]
                if isinstance(raw_submodel_ids, list) and raw_submodel_ids
                else _shell_submodel_ids(shell)
            )
            if handover_id not in submodel_ids:
                return []

            submodel_response = await client.get(f"/submodels/{_encode_id(handover_id)}")
            if submodel_response.status_code == 404:
                return []
            if submodel_response.status_code != 200:
                raise RuntimeError("AAS handover submodel could not be read")
            submodel = submodel_response.json()
            if not isinstance(submodel, dict) or submodel.get("id") != handover_id:
                raise RuntimeError("AAS handover submodel reference is invalid")
    except (httpx.RequestError, ValueError) as exc:
        raise RuntimeError("AAS visual asset references are unavailable") from exc

    visual_assets: list[dict[str, str]] = []
    pending: list[tuple[Any, int]] = [(submodel.get("submodelElements", []), 0)]
    visited = 0
    while pending and visited < 2048 and len(visual_assets) < 32:
        elements, depth = pending.pop()
        if depth > 12 or not isinstance(elements, list):
            continue
        for element in elements:
            visited += 1
            if visited > 2048:
                break
            if not isinstance(element, dict):
                continue
            if element.get("modelType") == "File":
                url = element.get("value")
                content_type = str(element.get("contentType") or "").split(";", 1)[0].strip().lower()
                if not isinstance(url, str):
                    continue
                if (
                    content_type == "text/html"
                    and re.fullmatch(
                        rf"/digital-twin-apps/{re.escape(normalized_lab_id)}/[a-f0-9]{{64}}/index\.html",
                        url,
                    )
                ):
                    renderer = "threejs-app"
                elif (
                    content_type == "model/gltf-binary"
                    and re.fullmatch(
                        rf"/digital-twin-scenes/{re.escape(normalized_lab_id)}/[a-f0-9]{{64}}\.glb",
                        url,
                    )
                ):
                    renderer = "glb"
                else:
                    continue
                visual_assets.append({
                    "submodelId": handover_id,
                    "elementIdShort": str(element.get("idShort") or ""),
                    "url": url,
                    "contentType": content_type,
                    "renderer": renderer,
                })
            elif isinstance(element.get("value"), list):
                pending.append((element["value"], depth + 1))
    return visual_assets


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
                raw_submodel_ids = shell.get("submodelIds")
                if isinstance(raw_submodel_ids, list):
                    submodel_ids = [
                        value.strip()
                        for value in raw_submodel_ids
                        if isinstance(value, str) and value.strip()
                    ]
                else:
                    submodel_ids = _shell_submodel_ids(shell)
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
                access_policy_id = _submodel_id_for_access_control(lab_id)
                if access_policy_id not in generated_shell["submodelIds"]:
                    access_policy = await client.get(
                        f"/submodels/{_encode_id(access_policy_id)}"
                    )
                    if access_policy.status_code == 200:
                        generated_shell["submodelIds"].append(access_policy_id)
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

async def _sync_aasx_package_resources(
    client: httpx.AsyncClient,
    result: dict,
    *,
    lab_id: str,
    access_key: str,
    metadata: dict,
    aasx_bytes: bytes,
    extra_info: Optional[dict],
    fmi_ls_resources: Optional[dict],
    fmu_path: Optional[Path],
    required_aas_id: Optional[str],
    force_regenerate_access_policy: bool,
) -> dict:
    """Validate and upload a provider AASX package and its contained resources."""
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

    aasx_simulation_model_id: str | None = None
    generate_access_policy = False
    if isinstance(metadata.get("modelVariables"), list):
        if force_regenerate_access_policy:
            result["error"] = "Access policy defaults cannot be regenerated while importing AASX"
            return result
        if not required_shell_id:
            result["error"] = "FMU AASX import requires its stable laboratory shell ID"
            return result
        target_shells = [
            shell for shell in all_shells
            if isinstance(shell, dict) and shell.get("id") == required_shell_id
        ]
        if len(target_shells) != 1:
            result["error"] = "FMU AASX must contain exactly one stable laboratory shell"
            return result
        target_shell = target_shells[0]

        simulation_models = [
            submodel for submodel in all_submodels
            if isinstance(submodel, dict) and submodel.get("idShort") == "SimulationModels"
        ]
        if len(simulation_models) > 1:
            result["error"] = "FMU AASX contains ambiguous SimulationModels submodels"
            return result
        if simulation_models:
            aasx_simulation_model_id = simulation_models[0].get("id")
            if not isinstance(aasx_simulation_model_id, str) or not aasx_simulation_model_id.strip():
                result["error"] = "FMU AASX SimulationModels submodel has no valid ID"
                return result
        else:
            generated_simulation_model = build_simulation_submodel(
                lab_id,
                access_key,
                metadata,
                extra_info,
                fmu_path=fmu_path,
            )
            aasx_simulation_model_id = generated_simulation_model["id"]
            all_submodels.append(generated_simulation_model)

        shell_refs = target_shell.get("submodels")
        if not isinstance(shell_refs, list):
            shell_refs = []
            target_shell["submodels"] = shell_refs
        if aasx_simulation_model_id not in _shell_submodel_ids(target_shell):
            shell_refs.append({
                "type": "ModelReference",
                "keys": [{"type": "Submodel", "value": aasx_simulation_model_id}],
            })

        generated_related_resources = build_fmi_ls_related_resources_submodel(
            lab_id,
            fmi_ls_resources,
        )
        if generated_related_resources is not None:
            related_candidates = [
                (index, submodel)
                for index, submodel in enumerate(all_submodels)
                if isinstance(submodel, dict)
                and (
                    submodel.get("idShort") == "FmiLsRelatedResources"
                    or any(
                        isinstance(key, dict)
                        and key.get("value") == _SEMANTIC_ID_FMI_LS_RELATED_RESOURCES
                        for key in (
                            submodel.get("semanticId", {}).get("keys", [])
                            if isinstance(submodel.get("semanticId"), dict)
                            else []
                        )
                    )
                )
            ]
            if len(related_candidates) > 1:
                result["error"] = "FMU AASX contains ambiguous FMI-LS-REF resource submodels"
                return result
            if related_candidates:
                related_index, related_existing = related_candidates[0]
                existing_id = related_existing.get("id")
                if not isinstance(existing_id, str) or not existing_id.strip():
                    result["error"] = "FMU AASX FMI-LS-REF resource submodel has no valid ID"
                    return result
                if any(
                    isinstance(key, dict)
                    and key.get("value") == _SEMANTIC_ID_FMI_LS_RELATED_RESOURCES
                    for key in (
                        related_existing.get("semanticId", {}).get("keys", [])
                        if isinstance(related_existing.get("semanticId"), dict)
                        else []
                    )
                ):
                    generated_related_resources["id"] = existing_id
                    all_submodels[related_index] = generated_related_resources
                else:
                    # Keep a provider-authored submodel with the same short
                    # name if it uses a different semantic contract.
                    generated_related_resources = related_existing
                related_id = existing_id
            else:
                related_id = generated_related_resources["id"]
                all_submodels.append(generated_related_resources)
            if related_id not in _shell_submodel_ids(target_shell):
                shell_refs.append({
                    "type": "ModelReference",
                    "keys": [{"type": "Submodel", "value": related_id}],
                })
            result["fmiLsRelatedResourcesSubmodelId"] = related_id

        imported_access_policies = [
            submodel for submodel in all_submodels
            if _is_simulation_access_control_submodel(submodel)
        ]
        if len(imported_access_policies) > 1:
            result["error"] = "FMU AASX contains ambiguous simulation access policies"
            return result
        if imported_access_policies:
            policy_submodel = imported_access_policies[0]
            policy_submodel_id = policy_submodel.get("id")
            shell_submodel_ids = set(_shell_submodel_ids(target_shell))
            if not isinstance(policy_submodel_id, str) or policy_submodel_id not in shell_submodel_ids:
                result["error"] = "FMU AASX access policy must be referenced by its laboratory shell"
                return result
            policy_elements = policy_submodel.get("submodelElements", [])
            policy_blobs = [
                element for element in policy_elements
                if isinstance(element, dict)
                and (
                    element.get("idShort") == "AllAccessPermissionRules"
                    or _decode_part4_access_rules_blob(element) is not None
                )
            ] if isinstance(policy_elements, list) else []
            if len(policy_blobs) != 1:
                result["error"] = "FMU AASX access policy must contain one Part 4 JSON Blob"
                return result
            rules_blob = policy_blobs[0]
            rules_document = _decode_part4_access_rules_blob(rules_blob)
            if rules_document is None:
                result["error"] = "FMU AASX access policy Blob is invalid"
                return result
            raw_rules = base64.b64decode(rules_blob["value"], validate=True)
            generated_digest = _find_property_value(policy_submodel, "GeneratedPolicyDigest")
            interface_digest = _find_property_value(policy_submodel, "InterfaceDigest")
            source = "aas-generated" if (
                generated_digest
                and generated_digest == hashlib.sha256(raw_rules).hexdigest()
            ) else "aas-provider"
            try:
                compile_part4_access_rules(
                    rules_document,
                    metadata,
                    aasx_simulation_model_id,
                    declared_interface_digest=interface_digest,
                    claims={},
                    source=source,
                    allowed_submodel_ids=shell_submodel_ids,
                )
            except (TypeError, ValueError) as exc:
                logger.warning("Imported FMU AASX access policy is invalid: %s", type(exc).__name__)
                result["error"] = "FMU AASX access policy does not match its FMU or AAS shell"
                return result
            result["accessPolicyPreserved"] = True
            result["accessControlSubmodelId"] = policy_submodel_id
        else:
            generate_access_policy = True
            generated_policy_id = _submodel_id_for_access_control(lab_id)
            if generated_policy_id not in _shell_submodel_ids(target_shell):
                shell_refs.append({
                    "type": "ModelReference",
                    "keys": [{"type": "Submodel", "value": generated_policy_id}],
                })

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

    if generate_access_policy:
        access_policy_result = await _sync_simulation_access_control(
            client,
            lab_id,
            metadata,
            simulation_model_submodel_id=aasx_simulation_model_id,
            force_regenerate=force_regenerate_access_policy,
        )
        if access_policy_result.get("error"):
            result["error"] = access_policy_result["error"]
            return result
        result["created"] = bool(result["created"] or access_policy_result.get("created"))
        result["updated"] = bool(result["updated"] or access_policy_result.get("updated"))
        result["accessControlSubmodelId"] = _submodel_id_for_access_control(lab_id)
        result["accessPolicyGenerated"] = True
        for flag in ("accessPolicyPreserved", "accessPolicyStale", "accessPolicyRegenerated"):
            if flag in access_policy_result:
                result[flag] = access_policy_result[flag]

    result["aasxUpload"] = True
    result["uploadedAasIds"] = uploaded_aas_ids
    result["uploadedSubmodelIds"] = uploaded_sm_ids
    if uploaded_aas_ids:
        result["aasId"] = uploaded_aas_ids[0]
    if uploaded_sm_ids:
        result["submodelId"] = uploaded_sm_ids[0]
    return result


async def _sync_generated_fmu_submodels(
    client: httpx.AsyncClient,
    result: dict,
    *,
    lab_id: str,
    access_key: str,
    metadata: dict,
    extra_info: Optional[dict],
    fmi_ls_resources: Optional[dict],
    fmu_path: Optional[Path],
    runtime_info: Optional[dict],
    force_regenerate_access_policy: bool,
) -> dict:
    """Build and upsert the generated FMU AAS resources."""
    aas_id = result["aasId"]
    submodel_id = result["submodelId"]
    technical_data_id = result["technicalDataSubmodelId"]
    access_control_id = result["accessControlSubmodelId"]
    execution_capabilities_id = result["executionSubmodelId"]
    interfaces_id = result["interfacesSubmodelId"]
    contact_id = result["contactSubmodelId"]
    handover_id = result["handoverSubmodelId"]
    related_resources_id = _submodel_id_for_fmi_ls_related_resources(lab_id)
    aas_id_encoded = _encode_id(aas_id)
    submodel_id_encoded = _encode_id(submodel_id)
    technical_data_id_encoded = _encode_id(technical_data_id)

    related_resources_payload = build_fmi_ls_related_resources_submodel(lab_id, fmi_ls_resources)
    shell_payload = build_aas_shell(
        lab_id,
        access_key,
        metadata,
        extra_info,
        fmi_ls_resources=fmi_ls_resources,
    )
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
    if related_resources_payload is not None:
        result["fmiLsRelatedResourcesSubmodelId"] = related_resources_id

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

    if isinstance(metadata.get("modelVariables"), list):
        result["accessControlSubmodelId"] = access_control_id
        access_policy_result = await _sync_simulation_access_control(
            client,
            lab_id,
            metadata,
            force_regenerate=force_regenerate_access_policy,
        )
        if access_policy_result.get("error"):
            result["error"] = access_policy_result["error"]
            return result
        result["created"] = bool(result["created"] or access_policy_result.get("created"))
        result["updated"] = bool(result["updated"] or access_policy_result.get("updated"))
        for flag in ("accessPolicyPreserved", "accessPolicyStale", "accessPolicyRegenerated"):
            if flag in access_policy_result:
                result[flag] = access_policy_result[flag]

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
        (related_resources_id, related_resources_payload, "FmiLsRelatedResources"),
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
    return result


async def sync_fmu_to_basyx(
    lab_id: str,
    access_key: str,
    metadata: dict,
    aasx_bytes: Optional[bytes] = None,
    extra_info: Optional[dict] = None,
    fmi_ls_resources: Optional[dict] = None,
    fmu_path: Optional[Path] = None,
    unit_definitions: Sequence[dict] = (),
    required_aas_id: Optional[str] = None,
    runtime_info: Optional[dict] = None,
    force_regenerate_access_policy: bool = False,
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
    access_control_id = _submodel_id_for_access_control(lab_id)
    execution_capabilities_id = _submodel_id_for_execution(lab_id)
    interfaces_id = _submodel_id_for_interfaces(lab_id)
    contact_id = _submodel_id_for_contact(lab_id)
    handover_id = _submodel_id_for_handover(lab_id)
    related_resources_id = _submodel_id_for_fmi_ls_related_resources(lab_id)

    result: dict = {
        "aasId": aas_id,
        "submodelId": submodel_id,
        "technicalDataSubmodelId": technical_data_id,
        "accessControlSubmodelId": access_control_id,
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
                result = await _sync_aasx_package_resources(
                    client,
                    result,
                    lab_id=lab_id,
                    access_key=access_key,
                    metadata=metadata,
                    aasx_bytes=aasx_bytes,
                    extra_info=extra_info,
                    fmi_ls_resources=fmi_ls_resources,
                    fmu_path=fmu_path,
                    required_aas_id=required_aas_id,
                    force_regenerate_access_policy=force_regenerate_access_policy,
                )
                if result.get("error"):
                    return result

            else:
                # ── Metadata path: auto-generate shell + submodel from FMU ──
                result = await _sync_generated_fmu_submodels(
                    client,
                    result,
                    lab_id=lab_id,
                    access_key=access_key,
                    metadata=metadata,
                    extra_info=extra_info,
                    fmi_ls_resources=fmi_ls_resources,
                    fmu_path=fmu_path,
                    runtime_info=runtime_info,
                    force_regenerate_access_policy=force_regenerate_access_policy,
                )
                if result.get("error"):
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
