"""
AAS shell and submodel generator for physical laboratory resources.

Generates BaSyx V2-compatible JSON payloads from host config and heartbeat data.
Uses IDTA Digital Nameplate and Generic Technical Data submodels for lab identity
and current operational status derived from the Lab Station heartbeat.
"""

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import requests
from secret_values import env_or_secret_file as _env_or_secret_file_impl
from heartbeat_readiness import capability_ready

logger = logging.getLogger("ops-worker.aas")


def _env_or_secret_file(name: str, default: str = "") -> str:
    return _env_or_secret_file_impl(name, default, logger=logger)


# Empty default: if not configured (e.g. Lite mode gateways without --profile aas),
# sync_lab_to_basyx returns a disabled result instead of attempting a connection.
BASYX_AAS_URL = os.getenv("BASYX_AAS_URL", "")
AAS_ALLOWED_HOSTS = os.getenv("AAS_ALLOWED_HOSTS", "")
AAS_SERVICE_TOKEN = _env_or_secret_file("AAS_SERVICE_TOKEN")
AAS_SERVICE_TOKEN_HEADER = os.getenv("AAS_SERVICE_TOKEN_HEADER", "Authorization")
_BUNDLED_AAS_URL = "http://basyx-aas-server:8081"

_BASYX_TIMEOUT = int(os.getenv("BASYX_AAS_TIMEOUT", "15"))
_AAS_LAB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_SEMANTIC_ID_NAMEPLATE = "https://admin-shell.io/idta/nameplate/3/0/Nameplate"
_SEMANTIC_ID_TECHNICAL_DATA = "0173-1#01-AHX837#002"
_SEMANTIC_ID_CAPABILITY_DESCRIPTION = "https://admin-shell.io/idta/SubmodelTemplate/CapabilityDescription/1/0"
_SEMANTIC_ID_ASSET_INTERFACES = "https://admin-shell.io/idta/AssetInterfacesDescription/1/1/Submodel"
_SEMANTIC_ID_CONTACT_INFORMATION = "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations"
_SEMANTIC_ID_HANDOVER_DOCUMENTATION = "0173-1#01-AHF578#003"
_SEMANTIC_ID_ARBITRARY_PROPERTY = "https://admin-shell.io/SMT/General/ArbitraryProp"


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


def _submodel_id_execution(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:executionCapabilities"


def _submodel_id_interfaces(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:assetInterfaces"


def _submodel_id_contact(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:contactInformation"


def _submodel_id_handover(lab_id: str) -> str:
    return f"urn:decentralabs:lab:{lab_id}:sm:handoverDocumentation"


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


def _metadata_text(extra_info: Optional[Dict[str, Any]], key: str) -> str:
    value = (extra_info or {}).get(key)
    return value.strip() if isinstance(value, str) else ""


def _metadata_documentation(extra_info: Optional[Dict[str, Any]]) -> list[str]:
    values = (extra_info or {}).get("documentationUrls", [])
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    ))


def build_nameplate_submodel(
    lab_id: str,
    host: Dict[str, Any],
    extra_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build IDTA 02006 v3.0 Digital Nameplate for a physical lab."""
    specific_values = [
        _arbitrary_prop("HostName", "xs:string", host.get("name", ""), "Station host name."),
        _arbitrary_prop("LabType", "xs:string", "PhysicalLaboratory", "DecentraLabs resource classification."),
        _arbitrary_prop("NetworkAddress", "xs:string", host.get("address", ""), "Station network address."),
    ]
    mac = host.get("mac")
    if mac:
        specific_values.append(_arbitrary_prop("MacAddress", "xs:string", mac, "Station network interface address."))
    elements = [
        _standard_prop("URIOfTheProduct", "xs:anyURI", _aas_id_for_lab(lab_id), "0112/2///61987#ABN590#002"),
        _standard_mlp("ManufacturerName", "DecentraLabs", "0112/2///61987#ABA565#009"),
        _standard_mlp("ManufacturerProductDesignation", str(host.get("name") or "Physical laboratory"), "0112/2///61987#ABA567#009"),
        _standard_prop("ManufacturerProductType", "xs:string", "PhysicalLaboratory", "0112/2///61987#ABA300#008"),
        _standard_prop("UniqueFacilityIdentifier", "xs:string", lab_id, "https://admin-shell.io/idta/nameplate/3/0/UniqueFacilityIdentifier"),
        {
            "idShort": "AssetSpecificProperties",
            "semanticId": _semantic_id("0173-1#02-ABI218#003/0173-1#01-AGZ672#004"),
            "modelType": "SubmodelElementCollection",
            "value": specific_values,
        },
    ]

    return {
        "id": _submodel_id_nameplate(lab_id),
        "idShort": "Nameplate",
        "modelType": "Submodel",
        "semanticId": _semantic_id(_SEMANTIC_ID_NAMEPLATE),
        "submodelElements": elements,
    }


def build_technical_data_submodel(
    lab_id: str,
    host: Dict[str, Any],
    heartbeat: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build IDTA 02003 v2.0.1 TechnicalData with arbitrary runtime values."""
    now_iso = datetime.now(timezone.utc).isoformat()
    hb = heartbeat or {}

    status = hb.get("status", {})
    operations = hb.get("operations", {})

    ready = capability_ready(hb, "physicalLab")
    local_mode = status.get("localModeEnabled")
    local_session = status.get("localSessionActive")
    hb_timestamp = hb.get("timestamp", "")

    last_power = operations.get("lastPowerAction") or {}
    last_power_ts = last_power.get("timestamp", "")
    last_power_mode = last_power.get("mode", "")

    last_logoff = operations.get("lastForcedLogoff") or {}
    last_logoff_ts = last_logoff.get("timestamp", "")
    last_logoff_user = last_logoff.get("user", "")

    resource_status = "Ready" if ready else ("NotReady" if ready is False else "Unknown")

    def bool_str(val: Any) -> str:
        if val is None:
            return ""
        return "true" if val else "false"

    elements = [
        {
            "idShort": "GeneralInformation",
            "semanticId": _semantic_id("0173-1#02-ABK161#002/0173-1#01-AHX838#002"),
            "modelType": "SubmodelElementCollection",
            "value": [
                _standard_prop("ManufacturerName", "xs:string", "DecentraLabs", "0173-1#02-AAO677#004"),
                _standard_mlp("ManufacturerProductDesignation", str(host.get("name") or "Physical laboratory"), "0173-1#02-AAW338#003"),
            ],
        },
        {
            "idShort": "TechnicalPropertyAreas",
            "semanticId": _semantic_id("0173-1#02-ABK163#002"),
            "modelType": "SubmodelElementList",
            "typeValueListElement": "SubmodelElementCollection",
            "value": [{
                "idShort": "OperationalStatus",
                "semanticId": _semantic_id("0173-1#02-ABL358#002/0173-1#01-AHX773#002"),
                "modelType": "SubmodelElementCollection",
                "value": [
                    _arbitrary_prop("ResourceType", "xs:string", "PhysicalLaboratory", "DecentraLabs resource classification."),
                    _arbitrary_prop("ResourceStatus", "xs:string", resource_status, "Current publication status."),
                    _arbitrary_prop("LabStatus", "xs:string", "Ready" if ready else ("NotReady" if ready is False else ""), "Physical lab readiness projection."),
                    _arbitrary_prop("LastPowerActionMode", "xs:string", last_power_mode, "Last power operation mode."),
                    _arbitrary_prop("LastForcedLogoffUser", "xs:string", last_logoff_user, "User affected by the last forced logoff."),
                    _arbitrary_prop("LastSyncTimestamp", "xs:dateTime", now_iso, "Timestamp of this AAS publication."),
                ],
            }],
        },
    ]

    operational_values = elements[1]["value"][0]["value"]
    if ready is not None:
        operational_values.append(
            _arbitrary_prop("ReadyFlag", "xs:boolean", bool_str(ready), "Whether the station reports readiness.")
        )
    if local_mode is not None:
        operational_values.append(
            _arbitrary_prop("LocalModeEnabled", "xs:boolean", bool_str(local_mode), "Whether local station mode is enabled.")
        )
    if local_session is not None:
        operational_values.append(
            _arbitrary_prop("LocalSessionActive", "xs:boolean", bool_str(local_session), "Whether a local station session is active.")
        )
    if hb_timestamp:
        operational_values.append(
            _arbitrary_prop("LastHeartbeatTimestamp", "xs:dateTime", hb_timestamp, "Last station heartbeat timestamp.")
        )
    if last_power_ts:
        operational_values.append(
            _arbitrary_prop("LastPowerActionTimestamp", "xs:dateTime", last_power_ts, "Last power operation timestamp.")
        )
    if last_logoff_ts:
        operational_values.append(
            _arbitrary_prop("LastForcedLogoffTimestamp", "xs:dateTime", last_logoff_ts, "Last forced logoff timestamp.")
        )

    return {
        "id": _submodel_id_technical(lab_id),
        "idShort": "TechnicalData",
        "modelType": "Submodel",
        "semanticId": _semantic_id(_SEMANTIC_ID_TECHNICAL_DATA),
        "submodelElements": elements,
    }


def _semantic_id(value: str) -> Dict[str, Any]:
    return {
        "type": "ExternalReference",
        "keys": [{"type": "GlobalReference", "value": value}],
    }


def _standard_prop(id_short: str, value_type: str, value: Any, semantic_id: str) -> Dict[str, Any]:
    element = _prop(id_short, value_type, value)
    element["semanticId"] = _semantic_id(semantic_id)
    return element


def _standard_mlp(id_short: str, value: str, semantic_id: str) -> Dict[str, Any]:
    return {
        "idShort": id_short,
        "semanticId": _semantic_id(semantic_id),
        "modelType": "MultiLanguageProperty",
        "value": [{"language": "en", "text": value}],
    }


def _arbitrary_prop(id_short: str, value_type: str, value: Any, description: str = "") -> Dict[str, Any]:
    element = _standard_prop(id_short, value_type, value, _SEMANTIC_ID_ARBITRARY_PROPERTY)
    if description:
        element["description"] = [{"language": "en", "text": description}]
    return element


def build_execution_capabilities_submodel(
    lab_id: str,
    host: Dict[str, Any],
    heartbeat: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the standard IDTA 02020 capability description for lab access."""
    capability_names = [
        ("PrepareAccessSession", "Prepare the station and gateway for an authorized laboratory access session."),
        ("StartInteractiveSession", "Start a reservation-authorized interactive laboratory session."),
        ("EndInteractiveSession", "End an interactive laboratory session and release its resources."),
        ("ReadOperationalStatus", "Read the latest published station heartbeat and readiness projection."),
    ]
    containers = [{
        "idShort": f"CapabilityContainer_{name}",
        "semanticId": _semantic_id("https://admin-shell.io/idta/CapabilityDescription/CapabilityContainer/1/0"),
        "modelType": "SubmodelElementCollection",
        "value": [{
            "idShort": name,
            "semanticId": _semantic_id("https://admin-shell.io/idta/CapabilityDescription/Capability/1/0"),
            "modelType": "Capability",
            "description": [{"language": "en", "text": description}],
        }],
    } for name, description in capability_names]
    return {
        "id": _submodel_id_execution(lab_id),
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


def _asset_interface_action(name: str, href: str, method: str = "POST", subprotocol: str = "") -> Dict[str, Any]:
    values = [
        _standard_prop("href", "xs:anyURI", href, "https://www.w3.org/2019/wot/hypermedia#hasTarget"),
        _standard_prop("htv_methodName", "xs:string", method, "https://www.w3.org/2011/http#methodName"),
    ]
    if subprotocol:
        values.append(_standard_prop("subprotocol", "xs:string", subprotocol, "https://www.w3.org/2019/wot/hypermedia#forSubProtocol"))
    return {
        "idShort": name,
        "semanticId": _semantic_id("https://www.w3.org/2019/wot/td#ActionAffordance"),
        "modelType": "SubmodelElementCollection",
        "value": [{
            "idShort": "forms",
            "semanticId": _semantic_id("https://www.w3.org/2019/wot/td#hasForm"),
            "modelType": "SubmodelElementCollection",
            "value": values,
        }],
    }


def build_asset_interfaces_description_submodel(
    lab_id: str,
    operations: list[tuple[str, str, str, str]],
    *,
    title: str = "DecentraLabs physical laboratory interface",
) -> Dict[str, Any]:
    actions = [_asset_interface_action(name, href, method, subprotocol) for name, href, method, subprotocol in operations]
    bearer_scheme = {
        "idShort": "bearer_sc",
        "semanticId": _semantic_id("https://www.w3.org/2019/wot/security#BearerSecurityScheme"),
        "modelType": "SubmodelElementCollection",
        "value": [
            _standard_prop("scheme", "xs:string", "bearer", "https://www.w3.org/2019/wot/security#SecurityScheme"),
            _standard_prop("name", "xs:string", "Authorization", "https://www.w3.org/2019/wot/security#name"),
            _standard_prop("in", "xs:string", "header", "https://www.w3.org/2019/wot/security#in"),
        ],
    }
    return {
        "id": _submodel_id_interfaces(lab_id),
        "idShort": "AssetInterfacesDescription",
        "modelType": "Submodel",
        "semanticId": _semantic_id(_SEMANTIC_ID_ASSET_INTERFACES),
        "submodelElements": [{
            "idShort": "InterfaceTemplateForHTTP",
            "semanticId": _semantic_id("https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Interface"),
            "modelType": "SubmodelElementCollection",
            "value": [
                _standard_prop("title", "xs:string", title, "https://www.w3.org/2019/wot/td#title"),
                {
                    "idShort": "EndpointMetadata",
                    "semanticId": _semantic_id("https://admin-shell.io/idta/AssetInterfacesDescription/1/0/EndpointMetadata"),
                    "modelType": "SubmodelElementCollection",
                    "value": [
                        _standard_prop("base", "xs:anyURI", "/ops/api/v1", "https://www.w3.org/2019/wot/td#baseURI"),
                        _standard_prop("contentType", "xs:string", "application/json", "https://www.w3.org/2019/wot/hypermedia#forContentType"),
                        {
                            "idShort": "securityDefinitions",
                            "semanticId": _semantic_id("https://www.w3.org/2019/wot/security#definesSecurityScheme"),
                            "modelType": "SubmodelElementCollection",
                            "value": [bearer_scheme],
                        },
                    ],
                },
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
        }],
    }


def build_contact_information_submodel(lab_id: str, extra_info: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    email = _metadata_text(extra_info, "contactEmail")
    if not email:
        return None
    values = []
    values.append({
        "idShort": "Email",
        "semanticId": _semantic_id("0173-1#02-AAQ836#005"),
        "modelType": "SubmodelElementCollection",
        "value": [_standard_prop("EmailAddress", "xs:string", email, "0173-1#02-AAO198#002")],
    })
    return {
        "id": _submodel_id_contact(lab_id),
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


def build_handover_documentation_submodel(lab_id: str, extra_info: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    urls = _metadata_documentation(extra_info)
    license_value = _metadata_text(extra_info, "license")
    if license_value.startswith(("http://", "https://")):
        urls.insert(0, license_value)
    documents = []
    if not urls:
        return None
    for index, url in enumerate(dict.fromkeys(urls)):
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
                    _standard_prop("DocumentDomainId", "xs:string", urlsplit(url).hostname or "decentralabs", "0173-1#02-ABH994#003"),
                    _standard_prop("DocumentIdentifier", "xs:string", url, "0173-1#02-AAO099#004"),
                ],
            }],
        }
        documents.append({
            "idShort": f"Document_{index}",
            "semanticId": _semantic_id("0173-1#02-ABI500#003/0173-1#01-AHF579#003"),
            "modelType": "SubmodelElementCollection",
            "value": [document_ids, {
                "idShort": "DocumentVersions",
                "semanticId": _semantic_id("0173-1#02-ABI503#003"),
                "modelType": "SubmodelElementList",
                "typeValueListElement": "SubmodelElementCollection",
                "value": [{
                    "idShort": "DocumentVersion_0",
                    "semanticId": _semantic_id("0173-1#02-ABI503#003/0173-1#01-AHF582#003"),
                    "modelType": "SubmodelElementCollection",
                    "value": [{
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
                    }, {
                        "idShort": "Version",
                        "semanticId": _semantic_id("0173-1#02-AAP003#005"),
                        "modelType": "Property",
                        "valueType": "xs:string",
                        "value": "1.0",
                    }, {
                        "idShort": "Title",
                        "semanticId": _semantic_id("0173-1#02-ABG940#003"),
                        "modelType": "MultiLanguageProperty",
                        "value": [{"language": "en", "text": "License terms" if url == license_value else f"Documentation {index + 1}"}],
                    }, {
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
                    }],
                }],
            }],
        })
    return {
        "id": _submodel_id_handover(lab_id),
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


def build_physical_aas_shell(
    lab_id: str,
    host: Dict[str, Any],
    extra_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the AAS shell for a physical lab resource."""
    aas_id = _aas_id_for_lab(lab_id)
    nameplate_id = _submodel_id_nameplate(lab_id)
    technical_id = _submodel_id_technical(lab_id)
    execution_id = _submodel_id_execution(lab_id)
    interfaces_id = _submodel_id_interfaces(lab_id)
    contact_id = _submodel_id_contact(lab_id)
    handover_id = _submodel_id_handover(lab_id)
    host_name = host.get("name", lab_id)
    description = _metadata_text(extra_info, "description") or (
        f"Physical lab resource '{host_name}' (labId={lab_id})"
    )
    return {
        "id": aas_id,
        "idShort": f"DecentraLabs_Lab_{lab_id}",
        "modelType": "AssetAdministrationShell",
        "assetInformation": {
            "assetKind": "Instance",
            "globalAssetId": aas_id,
        },
        "description": [{"language": "en", "text": description}],
        "submodels": [
            {"type": "ModelReference", "keys": [{"type": "Submodel", "value": nameplate_id}]},
            {"type": "ModelReference", "keys": [{"type": "Submodel", "value": technical_id}]},
            {"type": "ModelReference", "keys": [{"type": "Submodel", "value": execution_id}]},
            {"type": "ModelReference", "keys": [{"type": "Submodel", "value": interfaces_id}]},
            *(
                [{"type": "ModelReference", "keys": [{"type": "Submodel", "value": contact_id}]}]
                if _metadata_text(extra_info, "contactEmail")
                else []
            ),
            *(
                [{"type": "ModelReference", "keys": [{"type": "Submodel", "value": handover_id}]}]
                if _metadata_documentation(extra_info)
                or _metadata_text(extra_info, "license").startswith(("http://", "https://"))
                else []
            ),
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
    extra_info: Optional[Dict[str, Any]] = None,
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
    execution_id = _submodel_id_execution(lab_id)
    interfaces_id = _submodel_id_interfaces(lab_id)
    contact_id = _submodel_id_contact(lab_id)
    handover_id = _submodel_id_handover(lab_id)

    result: Dict[str, Any] = {
        "aasId": aas_id,
        "nameplateSubmodelId": nameplate_id,
        "technicalDataSubmodelId": technical_id,
        "executionSubmodelId": execution_id,
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

    shell_payload = build_physical_aas_shell(lab_id, host, extra_info)
    nameplate_payload = build_nameplate_submodel(lab_id, host, extra_info)
    technical_payload = build_technical_data_submodel(lab_id, host, heartbeat)
    execution_payload = build_execution_capabilities_submodel(lab_id, host, heartbeat)
    interfaces_payload = build_asset_interfaces_description_submodel(
        lab_id,
        [
            ("PrepareAccessSession", "/internal/guacamole/provision", "POST", ""),
            ("StartInteractiveSession", "/internal/guacamole/provision", "POST", ""),
            ("EndInteractiveSession", "/internal/guacamole/provision/{sessionId}", "DELETE", ""),
            ("ReadOperationalStatus", "/health", "GET", ""),
        ],
    )
    contact_payload = build_contact_information_submodel(lab_id, extra_info)
    handover_payload = build_handover_documentation_submodel(lab_id, extra_info)

    aas_id_enc = _encode_id(aas_id)
    np_id_enc = _encode_id(nameplate_id)
    td_id_enc = _encode_id(technical_id)
    execution_id_enc = _encode_id(execution_id)
    interfaces_id_enc = _encode_id(interfaces_id)
    contact_id_enc = _encode_id(contact_id)
    handover_id_enc = _encode_id(handover_id)

    session = None
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

        # --- CapabilityDescription submodel ---
        execution_result = _put_or_post(
            session,
            BASYX_AAS_URL,
            f"/submodels/{execution_id_enc}",
            "/submodels",
            execution_payload,
        )
        if "error" in execution_result:
            logger.error("Failed to sync CapabilityDescription submodel")
            result["error"] = "execution capabilities sync failed"
            return result
        logger.info("CapabilityDescription submodel synced (status=%s)", execution_result.get("status"))

        for _sm_id_enc, _sm_payload, _label in (
            (interfaces_id_enc, interfaces_payload, "AssetInterfacesDescription"),
            (contact_id_enc, contact_payload, "ContactInformations"),
            (handover_id_enc, handover_payload, "HandoverDocumentation"),
        ):
            if _sm_payload is None:
                continue
            _sm_result = _put_or_post(
                session,
                BASYX_AAS_URL,
                f"/submodels/{_sm_id_enc}",
                "/submodels",
                _sm_payload,
            )
            if "error" in _sm_result:
                logger.error("Failed to sync %s submodel", _label)
                result["error"] = f"{_label} sync failed"
                return result
            logger.info("%s submodel synced (status=%s)", _label, _sm_result.get("status"))

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
    finally:
        if session is not None:
            session.close()

    result["synced"] = True
    return result
