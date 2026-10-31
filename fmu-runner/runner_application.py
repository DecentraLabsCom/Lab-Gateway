"""
FMU Runner — FastAPI facade for remote FMI simulation services.

Endpoints:
  POST /api/v1/simulations/run      — Execute a simulation
  GET  /api/v1/simulations/describe — Describe FMU model metadata
  GET  /health                      — Health check
"""

import os
import time
import json
import logging
import asyncio
import re
from pathlib import Path
from typing import Any, NoReturn, Optional
from uuid import uuid4

import httpx
from fmpy import read_model_description
from fastapi import HTTPException, WebSocket, Request
from fastapi.responses import StreamingResponse

from auth import _fetch_jwks, verify_jwt, verify_jwt_token, jwks_health
from claim_values import (
    claim_reservation_key as _claim_reservation_key_value,
    coerce_epoch_seconds as _coerce_epoch_seconds_value,
    get_claim_lab_id as _get_claim_lab_id_value,
    normalize_lab_id as _normalize_lab_id_value,
)
from fmu_backend import LocalFmuMetadataBackend, StationFmuBackend
from fmu_path_resolver import (
    FmuPathResolutionError,
    _is_within_base,
    resolve_fmu_path as _resolve_fmu_path_impl,
)
from fmi_ls_ref import read_related_resources as _read_fmi_ls_related_resources
from fmi_ls_struct import read_fmi_ls_struct
from backend_factory import build_fmu_backend as _build_fmu_backend_impl
from execution_adapters import (
    reject_unsupported_remote_operation as _reject_unsupported_remote_operation_adapter,
    simulation_request_payload as _simulation_request_payload_adapter,
)
from local_fmu_catalog import (
    _list_local_fmus_payload as _catalog_list_local_fmus_payload,
    _load_local_model_metadata as _catalog_load_local_model_metadata,
    _local_metadata_backend_health_payload as _catalog_local_metadata_backend_health_payload,
)
from metadata import (
    _display_unit_inverse_map_from_fmu,
    _model_metadata_from_model_description,
    _normalize_xml_value,
    _parse_fmi_major_version,
    _public_model_metadata,
)
from proxy_fmu import (
    _build_proxy_model_description_xml,
    _collect_runtime_files as _collect_proxy_runtime_files,
    _proxy_model_identifier as _proxy_model_identifier_impl,
)
from proxy_artifact import build_proxy_artifact, build_proxy_artifact_headers
from proxy_session_config import (
    build_proxy_session_config as _build_proxy_session_config_impl,
    derive_gateway_ws_url as _derive_gateway_ws_url_impl,
)
from station_ws_proxy import StationRealtimeWsProxyManager
from realtime_factory import build_realtime_manager as _build_realtime_manager_impl
from proxy_rate_limiter import allow_download as _allow_proxy_download_impl
from session_ticket_responses import (
    extract_error_payload as _extract_error_payload,
    extract_error_text as _extract_error_text,
)
from session_ticket_payloads import (
    build_issue_session_ticket_payload as _build_issue_session_ticket_payload,
    build_redeem_session_ticket_payload as _build_redeem_session_ticket_payload,
)
from session_ticket_service import (
    issue_session_ticket as _issue_session_ticket_service,
    redeem_session_ticket as _redeem_session_ticket_service,
)
from session_ticket_transport import (
    build_session_ticket_headers as _build_session_ticket_headers_transport,
    post_session_ticket_request as _post_session_ticket_request_transport,
)
from session_ticket_values import normalize_ticket_id as _normalize_ticket_id_value
from session_observation_payloads import (
    build_session_observation_payload as _build_session_observation_payload,
)
from session_observation_service import (
    confirm_session_started as _confirm_session_started_service,
    confirm_session_started_with_retries as _confirm_session_started_with_retries,
    record_browser_session_started as _record_browser_session_started_service,
)
from session_observer_auth import (
    SessionObserverConfigurationError,
    create_session_observer_authorization,
)
from runner_runtime import create_fmu_runner_runtime
from simulation_request import SimulationRequest
from simulation_access_policy import filter_fmi_values, filter_model_description
from config import (
    _default_access_audit_url as _default_access_audit_url_value,
    CONFIG,
)
from fmu_app_factory import create_app
from lifecycle import create_lifespan
from health_router import create_health_router
from catalog_router import create_catalog_router
from history_router import create_history_router
from cancel_router import create_cancel_router
from run_router import create_run_router
from stream_router import create_stream_router, stream_authorized_simulation
from realtime_router import create_realtime_router
from aas_link_router import create_aas_link_router
from aas_hints_router import create_aas_hints_router
from aas_sync_router import create_aas_sync_router
from aasx_router import create_aasx_router
from aasx_catalog import AasxPackageCatalog
from aas_association_service import AasAssociationService
from aas_access_policy_resolver import AasAccessPolicyResolver
from proxy_router import create_proxy_router
from local_preview import PreviewTickets, create_preview_router
from local_preview_aasx import LocalPreviewAasxRegistry
from digital_twin_assets_router import create_digital_twin_assets_router, store_local_preview_assets

FMU_DATA_PATH = CONFIG.fmu_data_path
_DIGITAL_TWIN_ASSETS_PATH = CONFIG.digital_twin_assets_path
_LAB_MANAGER_TOKEN = CONFIG.lab_manager_token
_AAS_LINK_DATA_PATH = CONFIG.aas_link_data_path
_AAS_CATALOG_PATH = CONFIG.aas_catalog_path
WS_CLEANUP_SECONDS = CONFIG.ws_cleanup_seconds
INTERNAL_WS_TOKEN = CONFIG.internal_ws_token
AUTH_SESSION_TICKET_ISSUE_URL = CONFIG.auth_session_ticket_issue_url
AUTH_SESSION_TICKET_REDEEM_URL = CONFIG.auth_session_ticket_redeem_url
AUTH_SESSION_TICKET_INTERNAL_TOKEN = CONFIG.auth_session_ticket_internal_token
SESSION_OBSERVER_GATEWAY_ID = CONFIG.session_observer_gateway_id
SESSION_OBSERVER_SIGNING_SECRET = CONFIG.session_observer_signing_secret
ACCESS_AUDIT_URL = CONFIG.access_audit_url
FMU_PROXY_RUNTIME_PATH = CONFIG.fmu_proxy_runtime_path
FMU_PROXY_GATEWAY_WS_URL = CONFIG.fmu_proxy_gateway_ws_url
FMU_PROXY_SIGNING_KEY = CONFIG.fmu_proxy_signing_key
FMU_PROXY_TIME_MODE = CONFIG.fmu_proxy_time_mode
FMU_PROXY_PLAYBACK_SPEED = CONFIG.fmu_proxy_playback_speed
FMU_BACKEND_MODE = CONFIG.fmu_backend_mode
FMU_LOCAL_DEV_MODE = CONFIG.fmu_local_dev_mode
FMU_LOCAL_EXECUTOR_BASE_URL = CONFIG.fmu_local_executor_base_url
FMU_LOCAL_EXECUTOR_INTERNAL_TOKEN = CONFIG.fmu_local_executor_internal_token
_preview_tickets = PreviewTickets() if FMU_LOCAL_DEV_MODE else None
_LOCAL_PREVIEW_AASX_REGISTRY: Optional[LocalPreviewAasxRegistry] = None
FMU_STATION_BASE_URL = CONFIG.fmu_station_base_url
FMU_STATION_INTERNAL_TOKEN = CONFIG.fmu_station_internal_token
FMU_STATION_REQUEST_TIMEOUT: float = CONFIG.fmu_station_request_timeout
FMU_SESSION_OBSERVATION_MAX_ATTEMPTS = CONFIG.fmu_session_observation_max_attempts
PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE = CONFIG.proxy_download_rate_limit_per_minute
WS_CREATE_RATE_LIMIT_PER_MINUTE = CONFIG.ws_create_rate_limit_per_minute

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _default_access_audit_url() -> str:
    """Return the default observer URL derived from the redeem endpoint."""
    return _default_access_audit_url_value(AUTH_SESSION_TICKET_REDEEM_URL)


# ---- Structured JSON logging ----

class _JsonFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log, default=str)

_handler = logging.StreamHandler()
_handler.setFormatter(_JsonFormatter())
logger = logging.getLogger("fmu-runner")
logger.handlers.clear()
logger.addHandler(_handler)
logger.setLevel(logging.INFO)

def _normalize_ticket_id(session_ticket: Optional[str]) -> Optional[str]:
    return _normalize_ticket_id_value(session_ticket)


def _allow_proxy_download(key: str) -> bool:
    return _allow_proxy_download_impl(
        key,
        limit_per_minute=PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE,
        hits=_runner_runtime.proxy_download_hits,
        lock=_runner_runtime.proxy_download_lock,
        clock=time.time,
    )


_runner_runtime = create_fmu_runner_runtime()


async def _preload_jwks_if_enabled():
    enabled = os.getenv("JWKS_PRELOAD_ON_STARTUP", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }
    if not enabled:
        return False
    try:
        await _fetch_jwks(force=True)
    except HTTPException:
        logger.warning("JWKS preload failed; health will remain DOWN until keys are loaded")
        return False
    return True

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

async def _health_backend_payload(lab_id: Optional[str] = None):
    if lab_id is None:
        return await _runner_runtime.backend.health()
    return await _runner_runtime.backend.health(lab_id=lab_id)


async def _refresh_health_jwks():
    return await _fetch_jwks()


def _health_auth_status():
    return jwks_health()


def _catalog_enforce_fmu_claim(claims: dict, *, allow_provider_describe: bool = False):
    return _enforce_fmu_claim(claims, allow_provider_describe=allow_provider_describe)


async def _catalog_get_authorized_model_metadata(
    *,
    claims: dict,
    requested_fmu_filename: Optional[str] = None,
    include_internal_variables: bool = True,
):
    return await _runner_runtime.backend.get_authorized_model_metadata(
        claims=claims,
        requested_fmu_filename=requested_fmu_filename,
        include_internal_variables=include_internal_variables,
    )


async def _catalog_get_authorized_parameter_sets(*, claims: dict):
    return await _runner_runtime.backend.get_authorized_parameter_sets(claims=claims)


async def _catalog_get_authorized_experiments(*, claims: dict):
    return await _runner_runtime.backend.get_authorized_experiments(claims=claims)


async def _simulation_access_model_metadata(claims: dict) -> dict:
    """Read trusted FMI metadata once when the Executor session is created."""
    filename = str(claims.get("accessKey") or claims.get("fmuFileName") or "").strip()
    if not filename:
        raise HTTPException(status_code=403, detail="Token has no authorised FMU file")
    return await _runner_runtime.backend.get_authorized_model_metadata(
        claims=claims,
        requested_fmu_filename=filename,
        include_internal_variables=True,
    )


async def _simulation_effective_access_policy_for_metadata(claims: dict, metadata: dict) -> dict:
    """Resolve current AAS permissions against the active session's FMI interface."""
    try:
        if not isinstance(metadata, dict) or not isinstance(metadata.get("modelVariables"), list):
            raise ValueError("authorized FMI metadata is invalid")
        policy = await _get_aas_access_policy_resolver().resolve(claims, metadata)
        public_metadata = _public_model_metadata(metadata)
        visible_description = filter_model_description(policy, public_metadata)
        policy["modelDescription"] = visible_description
        policy["modelVariables"] = visible_description.get("modelVariables", [])
        if "fmiLsStruct" in visible_description:
            policy["fmiLsStruct"] = visible_description["fmiLsStruct"]
        else:
            policy.pop("fmiLsStruct", None)
        return policy
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("FMU access policy could not be resolved: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="FMU access policy is unavailable") from exc


async def _simulation_effective_access_policy(claims: dict) -> dict:
    """Resolve the Gateway-enforced policy from the authorized FMU metadata."""
    try:
        metadata = await _simulation_access_model_metadata(claims)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("FMU metadata could not be read for access policy: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="FMU access policy is unavailable") from exc
    return await _simulation_effective_access_policy_for_metadata(claims, metadata)


def _catalog_public_model_metadata(metadata: dict):
    return _public_model_metadata(metadata)


async def _catalog_list_authorized_fmu(*, claims: dict):
    return await _runner_runtime.backend.list_authorized_fmu(claims=claims)


def _history_enforce_fmu_claim(claims: dict):
    return _enforce_fmu_claim(claims)


def _history_reject_unsupported_remote_operation(feature_name: str):
    return _reject_unsupported_remote_operation_adapter(feature_name, _runner_runtime.backend.mode)


def _aas_link_path_for_router(access_key: str) -> Path:
    return _aas_link_path(access_key)


_aasx_catalog = AasxPackageCatalog(_AAS_CATALOG_PATH)


def _record_aasx_association(**kwargs):
    return _aasx_catalog.record(**kwargs)


def _aas_hints_resolve_fmu_path(access_key: str):
    return _resolve_fmu_path(access_key)


def _aas_hints_read_model_description(fmu_path):
    return read_model_description(str(fmu_path))


async def _aas_fmu_model_metadata(access_key: str):
    return await _runner_runtime.backend.get_authorized_model_metadata(
        claims={"accessKey": access_key},
        requested_fmu_filename=access_key,
        include_internal_variables=True,
    )


async def _aas_fmu_related_resources(access_key: str) -> dict[str, Any]:
    return await _runner_runtime.backend.get_authorized_related_resources(
        claims={"accessKey": access_key},
    )


async def _aas_sync_access_policy_status(lab_id: str, access_key: str) -> dict:
    metadata = await _aas_fmu_model_metadata(access_key)
    return await _get_aas_access_policy_resolver().inspect(
        {"labId": str(lab_id), "accessKey": access_key},
        metadata,
    )


def _aas_sync_resolve_fmu_path(access_key: str):
    return _resolve_fmu_path(access_key)


def _aas_sync_read_model_description(fmu_path):
    return read_model_description(str(fmu_path))


def _aas_sync_metadata_builder(model_description):
    return _model_metadata_from_model_description(
        model_description,
        include_internal_variables=True,
    )


async def _aas_sync_to_basyx(**kwargs):
    from fmu_aas_generator import sync_fmu_to_basyx

    return await sync_fmu_to_basyx(**kwargs)


async def _aas_delete_resources(**kwargs):
    from fmu_aas_generator import delete_aasx_resources

    return await delete_aasx_resources(**kwargs)


async def _aas_serialize_resources(**kwargs):
    from fmu_aas_generator import serialize_aasx_resources

    return await serialize_aasx_resources(**kwargs)


async def _aas_discover_shells():
    from fmu_aas_generator import discover_basyx_shells

    return await discover_basyx_shells()


async def _aas_sync_runtime_status(lab_id: str):
    """Return bounded runner status to publish in the generated AAS."""
    del lab_id
    return dict(await _runner_runtime.backend.health())


_health_router = create_health_router(
    backend_health=_health_backend_payload,
    refresh_jwks=_refresh_health_jwks,
    auth_health=_health_auth_status,
)
_catalog_router = create_catalog_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_catalog_enforce_fmu_claim,
    get_authorized_model_metadata=_catalog_get_authorized_model_metadata,
    get_authorized_parameter_sets=_catalog_get_authorized_parameter_sets,
    get_authorized_experiments=_catalog_get_authorized_experiments,
    public_model_metadata=_catalog_public_model_metadata,
    list_authorized_fmu=_catalog_list_authorized_fmu,
    get_effective_policy=_simulation_effective_access_policy,
)
_aas_link_router = create_aas_link_router(
    get_link_path=_aas_link_path_for_router,
    invalidate_access_policy=lambda: _invalidate_aas_access_policy(),
)
_aas_hints_router = create_aas_hints_router(
    resolve_fmu_path=_aas_hints_resolve_fmu_path,
    read_model_description=_aas_hints_read_model_description,
    normalize_xml_value=_normalize_xml_value,
    logger=logger,
    get_model_metadata=_aas_fmu_model_metadata,
)
_aas_sync_router = create_aas_sync_router(
    resolve_fmu_path=_aas_sync_resolve_fmu_path,
    read_model_description=_aas_sync_read_model_description,
    metadata_builder=_aas_sync_metadata_builder,
    get_model_metadata=_aas_fmu_model_metadata,
    get_fmi_ls_related_resources=_aas_fmu_related_resources,
    sync_fmu_to_basyx=_aas_sync_to_basyx,
    get_runtime_status=_aas_sync_runtime_status,
    logger=logger,
    record_aasx=_record_aasx_association,
    invalidate_access_policy=lambda lab_id=None: _invalidate_aas_access_policy(lab_id),
    get_access_policy_status=_aas_sync_access_policy_status,
)
_aasx_router = create_aasx_router(
    association_service=AasAssociationService(
        package_catalog=_aasx_catalog,
        link_data_path=_AAS_LINK_DATA_PATH,
        discover_basyx_shells=_aas_discover_shells,
        delete_resources=_aas_delete_resources,
    ),
    serialize_resources=_aas_serialize_resources,
)
_digital_twin_assets_router = create_digital_twin_assets_router(
    asset_root=_DIGITAL_TWIN_ASSETS_PATH,
    lab_manager_token=_LAB_MANAGER_TOKEN,
    fmu_backend_mode=FMU_BACKEND_MODE,
    fmu_data_root=Path(FMU_DATA_PATH),
    resolve_local_fmu_path=lambda access_key: _resolve_fmu_path(access_key),
    station_base_url=FMU_STATION_BASE_URL,
    station_internal_token=FMU_STATION_INTERNAL_TOKEN,
    station_request_timeout=FMU_STATION_REQUEST_TIMEOUT,
    get_model_metadata=_aas_fmu_model_metadata,
)


# ----- helpers -----



def _normalize_lab_id(value) -> Optional[str]:
    return _normalize_lab_id_value(value)


def _get_claim_lab_id(claims: dict) -> Optional[str]:
    return _get_claim_lab_id_value(claims, normalizer=_normalize_lab_id)


_PROVIDER_DESCRIBE_SCOPE = "fmu:describe"
_PROVIDER_DESCRIBE_PURPOSE = "provider-describe"


def _is_provider_describe_claim(claims: dict) -> bool:
    """Return whether claims identify the short-lived metadata-only token."""
    return (
        str(claims.get("resourceType") or "").strip().lower() == "fmu"
        and str(claims.get("scope") or "").strip() == _PROVIDER_DESCRIBE_SCOPE
        and str(claims.get("purpose") or "").strip() == _PROVIDER_DESCRIBE_PURPOSE
        and bool(str(claims.get("accessKey") or "").strip())
    )


def _enforce_fmu_claim(claims: dict, *, allow_provider_describe: bool = False):
    if str(claims.get("resourceType") or "").lower() != "fmu":
        raise HTTPException(status_code=403, detail="Token is not authorised for FMU endpoints")
    if allow_provider_describe and _is_provider_describe_claim(claims):
        return
    missing = [
        name for name in ("labId", "accessKey", "reservationKey", "pucHash")
        if not str(claims.get(name) or "").strip()
    ]
    if missing:
        raise HTTPException(status_code=403, detail=f"Token is missing required FMU claims: {', '.join(missing)}")


def _claim_reservation_key(claims: dict) -> str:
    return _claim_reservation_key_value(claims)


def _enforce_requested_reservation(claims: dict, requested: Optional[str]) -> str:
    claim_reservation = _claim_reservation_key(claims)
    requested_reservation = str(requested or "").strip().lower()
    if requested_reservation and requested_reservation != claim_reservation:
        raise HTTPException(status_code=403, detail="Token is not authorised for requested reservationKey")
    return claim_reservation


def _coerce_epoch_seconds(value) -> Optional[int]:
    return _coerce_epoch_seconds_value(value)


def _resolve_fmu_path(fmu_filename: str) -> Path:
    """Resolve an authorised FMU access key within *FMU_DATA_PATH*."""
    try:
        return _resolve_fmu_path_impl(
            fmu_filename,
            FMU_DATA_PATH,
            validate_access_key=StationFmuBackend.validate_access_key,
        )
    except FmuPathResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

def _extract_authorization_header(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth
    return None


def _derive_gateway_ws_url(claims: dict) -> str:
    try:
        return _derive_gateway_ws_url_impl(
            claims,
            configured_url=FMU_PROXY_GATEWAY_WS_URL,
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _build_proxy_session_config(
    *,
    fmi_version: str,
    gateway_ws_url: str,
    lab_id: str,
    reservation_key: str,
    session_ticket: str,
    ticket_expires_at: int,
    time_mode: str = FMU_PROXY_TIME_MODE,
    playback_speed: float = FMU_PROXY_PLAYBACK_SPEED,
) -> dict[str, Any]:
    return _build_proxy_session_config_impl(
        fmi_version=fmi_version,
        gateway_ws_url=gateway_ws_url,
        lab_id=lab_id,
        reservation_key=reservation_key,
        session_ticket=session_ticket,
        ticket_expires_at=ticket_expires_at,
        time_mode=time_mode,
        playback_speed=playback_speed,
    )


def _local_metadata_backend_health_payload(lab_id: Optional[str] = None) -> dict:
    del lab_id
    return _catalog_local_metadata_backend_health_payload(
        data_path=FMU_DATA_PATH,
    )


def _load_local_model_metadata(
    fmu_filename: str,
    *,
    include_internal_variables: bool = True,
) -> dict:
    metadata = _catalog_load_local_model_metadata(
        fmu_filename,
        resolve_fmu_path=_resolve_fmu_path,
        model_description_reader=read_model_description,
        model_metadata_builder=_model_metadata_from_model_description,
        logger=logger,
        display_unit_inverse_reader=_display_unit_inverse_map_from_fmu,
        include_internal_variables=include_internal_variables,
    )
    fmi_ls_struct = read_fmi_ls_struct(
        _resolve_fmu_path(fmu_filename),
        fmi_version=str(metadata.get("fmiVersion") or ""),
        variable_names=[
            variable["name"]
            for variable in metadata.get("modelVariables", [])
            if isinstance(variable, dict) and isinstance(variable.get("name"), str)
        ],
    )
    if fmi_ls_struct is not None:
        metadata["fmiLsStruct"] = fmi_ls_struct
    return metadata


def _list_local_fmus_payload(claimed_file: str) -> dict:
    return _catalog_list_local_fmus_payload(
        claimed_file,
        data_path=FMU_DATA_PATH,
        resolve_fmu_path=_resolve_fmu_path,
        is_within_base=_is_within_base,
    )


def _load_local_fmi_ls_related_resources(fmu_filename: str) -> dict[str, Any]:
    return _read_fmi_ls_related_resources(_resolve_fmu_path(fmu_filename))


def _build_fmu_backend():
    return _build_fmu_backend_impl(
        mode=FMU_BACKEND_MODE,
        local_dev_mode=FMU_LOCAL_DEV_MODE,
        local_executor_base_url=FMU_LOCAL_EXECUTOR_BASE_URL,
        local_executor_internal_token=FMU_LOCAL_EXECUTOR_INTERNAL_TOKEN,
        station_base_url=FMU_STATION_BASE_URL,
        station_internal_token=FMU_STATION_INTERNAL_TOKEN,
        station_request_timeout=FMU_STATION_REQUEST_TIMEOUT,
        health_loader=_local_metadata_backend_health_payload,
        model_metadata_loader=_load_local_model_metadata,
        list_loader=_list_local_fmus_payload,
        related_resources_loader=_load_local_fmi_ls_related_resources,
        logger=logger,
        station_backend_factory=StationFmuBackend,
        local_metadata_backend_factory=LocalFmuMetadataBackend,
    )


def _get_station_backend() -> StationFmuBackend:
    if isinstance(_runner_runtime.backend, StationFmuBackend):
        return _runner_runtime.backend
    raise HTTPException(status_code=503, detail="No remote FMU Executor is configured")


def _simulation_request_payload(req: SimulationRequest, sim_id: Optional[str] = None) -> dict:
    return _simulation_request_payload_adapter(
        reservation_key=req.reservationKey,
        lab_id=req.labId,
        parameters=req.parameters,
        options=req.options,
        input_schedule=req.inputSchedule,
        sim_id=sim_id,
    )


def _reject_unsupported_remote_operation(feature_name: str) -> NoReturn:
    return _reject_unsupported_remote_operation_adapter(feature_name, _runner_runtime.backend.mode)


def _get_scoped_station_backend(feature_name: str) -> StationFmuBackend:
    if isinstance(_runner_runtime.backend, StationFmuBackend):
        return _runner_runtime.backend
    _reject_unsupported_remote_operation(feature_name)


async def _stream_station_simulation(
    request: Request,
    req: SimulationRequest,
    claims: dict,
    access_policy: Optional[dict] = None,
    *,
    is_local_preview: bool = False,
):
    station_backend = _get_station_backend()
    authorization = _extract_authorization_header(request)
    station_backend.build_authorized_context(
        claims=claims,
        requested_lab_id=req.labId,
        requested_reservation_key=req.reservationKey,
    )
    sim_id = uuid4().hex
    # Only the local-preview route may skip production session observations.
    # A claim value alone is never sufficient to select this exception.
    if not is_local_preview:
        await _record_browser_session_started(request, claims, sim_id)
    client, response = await station_backend.open_authorized_simulation_stream(
        claims=claims,
        request_payload=_simulation_request_payload(req, sim_id),
        authorization=authorization,
    )
    media_type = response.headers.get("content-type") or "application/x-ndjson"
    normalized_media_type = media_type.split(";", 1)[0].strip().lower()
    is_ndjson = normalized_media_type in {"application/x-ndjson", "application/ndjson"}
    if access_policy is not None and not is_ndjson and normalized_media_type != "application/json":
        await response.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail="FMU stream format cannot be safely filtered")

    async def _forward_stream():
        try:
            if access_policy is None:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
                return

            async for line in response.aiter_lines():
                if not line:
                    if is_ndjson:
                        yield b"\n"
                    continue
                try:
                    payload = json.loads(line)
                except (TypeError, ValueError):
                    logger.warning("FMU stream contained a non-JSON line; closing protected stream")
                    return
                filtered = filter_fmi_values(access_policy, payload)
                suffix = b"\n" if is_ndjson else b""
                yield json.dumps(filtered, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + suffix
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(_forward_stream(), media_type=media_type)


def _collect_runtime_files(*, fmi_version: str, model_identifier: str) -> list[tuple[Path, str]]:
    return _collect_proxy_runtime_files(
        runtime_path=FMU_PROXY_RUNTIME_PATH,
        fmi_version=fmi_version,
        model_identifier=model_identifier,
    )


async def _issue_session_ticket(
    authorization: str,
    *,
    lab_id: str,
    reservation_key: Optional[str],
    request_id: Optional[str] = None,
) -> tuple[str, int]:
    return await _issue_session_ticket_service(
        authorization,
        lab_id=lab_id,
        reservation_key=reservation_key,
        request_id=request_id,
        issue_url=AUTH_SESSION_TICKET_ISSUE_URL,
        build_payload=_build_issue_session_ticket_payload,
        post_request=_post_session_ticket_request,
        extract_error_text=_extract_response_error_text,
        coerce_epoch_seconds=_coerce_epoch_seconds,
        normalize_ticket_id=_normalize_ticket_id,
        logger=logger,
    )


async def _redeem_session_ticket(
    *,
    session_ticket: str,
    lab_id: Optional[str],
    reservation_key: Optional[str],
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> dict:
    if _preview_tickets is not None and session_ticket.startswith("preview_"):
        if lab_id is None or reservation_key is None:
            raise HTTPException(status_code=403, detail="Preview reservation mismatch")
        return dict(_preview_tickets.redeem(session_ticket, lab_id, reservation_key))
    return await _redeem_session_ticket_service(
        session_ticket=session_ticket,
        lab_id=lab_id,
        reservation_key=reservation_key,
        session_id=session_id,
        request_id=request_id,
        redeem_url=AUTH_SESSION_TICKET_REDEEM_URL,
        build_payload=_build_redeem_session_ticket_payload,
        post_request=_post_session_ticket_request,
        observer_authorization=_session_observer_authorization,
        extract_error_payload=_extract_response_error_payload,
        normalize_ticket_id=_normalize_ticket_id,
        logger=logger,
    )


def _session_observer_authorization() -> str:
    try:
        return create_session_observer_authorization(
            SESSION_OBSERVER_GATEWAY_ID,
            SESSION_OBSERVER_SIGNING_SECRET,
        )
    except SessionObserverConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "SESSION_OBSERVER_NOT_CONFIGURED", "error": str(exc)},
        ) from exc


async def _confirm_fmu_session_started(
    *,
    session_ticket: str,
    claims: dict,
    session_id: str,
    reservation_key: Optional[str] = None,
    request_id: Optional[str] = None,
) -> bool:
    if _preview_tickets is not None and session_ticket.startswith("preview_") and claims.get("sub") == "local-preview":
        return True
    return await _confirm_session_started_service(
        session_ticket=session_ticket,
        claims=claims,
        session_id=session_id,
        reservation_key=reservation_key,
        request_id=request_id,
        audit_url=ACCESS_AUDIT_URL,
        build_payload=_build_session_observation_payload,
        post_observation=_post_session_observation,
        observer_authorization=_session_observer_authorization,
        extract_error_payload=_extract_response_error_payload,
        observed_at=lambda: int(time.time()),
        normalize_ticket_id=_normalize_ticket_id,
        logger=logger,
    )


async def _record_browser_session_started(request: Request, claims: dict, sim_id: str) -> bool:
    """Durably observe the first accepted browser execution for one credential."""
    return await _record_browser_session_started_service(
        request,
        claims,
        sim_id,
        observation_lock=_runner_runtime.observation_lock,
        observed_credentials=_runner_runtime.observed_credentials,
        extract_authorization=_extract_authorization_header,
        issue_session_ticket=_issue_session_ticket,
        redeem_session_ticket=_redeem_session_ticket,
        retry_confirmation=_confirm_session_started_with_retries,
        confirm_session=_confirm_fmu_session_started,
        max_attempts=FMU_SESSION_OBSERVATION_MAX_ATTEMPTS,
        sleep=asyncio.sleep,
    )


def _build_session_ticket_headers(*, authorization: Optional[str] = None) -> dict[str, str]:
    return _build_session_ticket_headers_transport(
        authorization=authorization,
        internal_token=AUTH_SESSION_TICKET_INTERNAL_TOKEN,
    )


async def _post_session_ticket_request(
    url: str,
    *,
    payload: dict[str, Any],
    authorization: Optional[str] = None,
) -> httpx.Response:
    return await _post_session_ticket_request_transport(
        url,
        payload=payload,
        authorization=authorization,
        internal_token=AUTH_SESSION_TICKET_INTERNAL_TOKEN,
    )


async def _post_session_observation(
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any],
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10) as client:
        return await client.post(url, headers=headers, json=json)


def _extract_response_error_text(response: httpx.Response) -> str:
    return _extract_error_text(response)


def _extract_response_error_payload(response: httpx.Response) -> dict[str, Any]:
    return _extract_error_payload(response)


_runner_runtime.bind_backend(_build_fmu_backend())


class _UnsupportedRealtimeManager:
    def __init__(self, reason: Optional[str] = None):
        self.reason = reason

    async def start(self):
        return

    async def stop(self):
        return

    async def handle_websocket(self, websocket: WebSocket, *, internal: bool):
        await websocket.accept()
        message = self.reason or (
            f"Realtime FMU sessions are not wired for FMU_BACKEND_MODE={_runner_runtime.backend.mode}. "
            "Configure a remote Station or FMU Executor service."
        )
        await websocket.send_json({
            "type": "error",
            "code": "NOT_IMPLEMENTED",
            "message": message,
            "retryable": False,
        })
        await websocket.close(code=1013)


_runner_runtime.bind_realtime_manager(_build_realtime_manager_impl(
    backend=_runner_runtime.backend,
    logger=logger,
    verify_jwt_token=verify_jwt_token,
    enforce_fmu_claim=_enforce_fmu_claim,
    get_claim_lab_id=_get_claim_lab_id,
    normalize_lab_id=_normalize_lab_id,
    coerce_epoch_seconds=_coerce_epoch_seconds,
    redeem_session_ticket=_redeem_session_ticket,
    issue_session_ticket=_issue_session_ticket,
    confirm_session_started=_confirm_fmu_session_started,
    get_effective_policy=_simulation_effective_access_policy,
    get_session_model_metadata=_simulation_access_model_metadata,
    get_effective_policy_for_metadata=_simulation_effective_access_policy_for_metadata,
    ws_cleanup_seconds=WS_CLEANUP_SECONDS,
    internal_ws_token=INTERNAL_WS_TOKEN,
    ws_create_rate_limit_per_minute=WS_CREATE_RATE_LIMIT_PER_MINUTE,
    station_manager_factory=StationRealtimeWsProxyManager,
    unsupported_manager_factory=_UnsupportedRealtimeManager,
))


# ----- routes -----


# ── AAS Admin ────────────────────────────────────────────────────────
# Protected by OpenResty lab_manager_admin_access.lua — no JWT needed here.

# ── AAS Link: map a lab/FMU to an externally-managed AAS ─────────────

def _validate_storage_key(value: str, field_name: str) -> str:
    """Validate a user-controlled key before using it as a storage filename."""
    text = str(value or "").strip()
    if (
        not text
        or len(text) > 255
        or text in {".", ".."}
        or Path(text).name != text
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", text)
    ):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")
    # Return the basename produced by pathlib after the strict single-segment
    # validation.  Callers never use the original request value as a path.
    return Path(text).name


def _aas_link_path(access_key: str) -> Path:
    """Return the filesystem path for an AAS link override file."""
    safe = _validate_storage_key(access_key, "AAS link key")
    base = _AAS_LINK_DATA_PATH.resolve()
    # `safe` is a single validated filename segment and the containment check
    # below also protects against unexpected filesystem/symlink behavior.
    # codeql[py/path-injection]
    candidate = (base / f"{safe}.aas-link.json").resolve()
    if not _is_within_base(base, candidate):
        raise HTTPException(status_code=400, detail="Invalid AAS link key")
    return candidate


_AAS_ACCESS_POLICY_RESOLVER: Optional[AasAccessPolicyResolver] = None


def _get_aas_access_policy_resolver() -> AasAccessPolicyResolver:
    global _AAS_ACCESS_POLICY_RESOLVER
    if _AAS_ACCESS_POLICY_RESOLVER is None:
        import fmu_aas_generator

        _AAS_ACCESS_POLICY_RESOLVER = AasAccessPolicyResolver(
            get_basyx_url=lambda: fmu_aas_generator.BASYX_AAS_URL,
            get_request_headers=fmu_aas_generator._aas_request_headers,
            get_link_path=_aas_link_path,
        )
    return _AAS_ACCESS_POLICY_RESOLVER


def _invalidate_aas_access_policy(lab_id: Optional[str] = None) -> None:
    resolver = _get_aas_access_policy_resolver()
    resolver.invalidate(lab_id)


def _get_local_preview_aasx_registry() -> LocalPreviewAasxRegistry:
    global _LOCAL_PREVIEW_AASX_REGISTRY
    preview_tickets = _preview_tickets
    if not FMU_LOCAL_DEV_MODE or preview_tickets is None:
        raise HTTPException(status_code=404, detail="Local FMU preview is disabled")
    if _LOCAL_PREVIEW_AASX_REGISTRY is None:
        import fmu_aas_generator

        async def get_preview_model_metadata(access_key: str) -> dict:
            if preview_tickets is None:
                raise HTTPException(status_code=404, detail="Local FMU preview is disabled")
            claims = preview_tickets.claims_for_access_key(access_key)
            return await _runner_runtime.backend.get_authorized_model_metadata(
                claims=claims,
                requested_fmu_filename=access_key,
                include_internal_variables=True,
            )

        def get_local_preview_digital_twin_assets(lab_id: str, access_key: str):
            if FMU_BACKEND_MODE != "local":
                return []
            return store_local_preview_assets(
                root=_DIGITAL_TWIN_ASSETS_PATH,
                lab_id=lab_id,
                access_key=access_key,
                fmu_data_root=Path(FMU_DATA_PATH),
                resolve_local_fmu_path=_resolve_fmu_path,
            )

        _LOCAL_PREVIEW_AASX_REGISTRY = LocalPreviewAasxRegistry(
            get_model_metadata=get_preview_model_metadata,
            sync_fmu_to_basyx=_aas_sync_to_basyx,
            serialize_aasx_resources=_aas_serialize_resources,
            record_aasx=_record_aasx_association,
            get_aasx_package=_aasx_catalog.get,
            get_link_path=_aas_link_path,
            build_aas_shell=fmu_aas_generator.build_aas_shell,
            get_effective_policy=_simulation_effective_access_policy,
            invalidate_access_policy=_invalidate_aas_access_policy,
            get_digital_twin_assets=get_local_preview_digital_twin_assets,
            get_fmi_ls_related_resources=_aas_fmu_related_resources,
        )
    return _LOCAL_PREVIEW_AASX_REGISTRY


async def _ensure_local_preview_aas_policy(claims: dict) -> dict:
    return await _get_local_preview_aasx_registry().ensure(claims)


async def _local_preview_access_payload(
    claims: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    raw_variables: Any = policy.get("variables")
    variables: dict[str, Any] = raw_variables if isinstance(raw_variables, dict) else {}
    visible_permissions = {
        name: permission
        for name, permission in variables.items()
        if isinstance(name, str)
        and isinstance(permission, dict)
        and (permission.get("read") is True or bool(permission.get("writeAt")))
    }
    model_description = policy.get("modelDescription")
    if not isinstance(model_description, dict):
        model_description = {}
    model_variables = model_description.get("modelVariables", policy.get("modelVariables"))
    import fmu_aas_generator

    visual_assets = await fmu_aas_generator.get_handover_visual_assets(str(claims.get("labId") or ""))
    return {
        **model_description,
        "policySource": policy.get("policySource", "unavailable"),
        "policyVersion": policy.get("policyVersion", ""),
        "labId": claims.get("labId"),
        "accessKey": claims.get("accessKey"),
        "variables": visible_permissions,
        "modelVariables": model_variables if isinstance(model_variables, list) else [],
        "visualAssets": visual_assets,
    }


async def _local_preview_stream_simulation(
    request: Request,
    payload: Any,
    claims: dict,
    _prepared_policy: dict,
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Simulation request must be a JSON object")
    normalized = {
        **payload,
        "labId": claims["labId"],
        "reservationKey": claims["reservationKey"],
    }
    try:
        simulation_request = SimulationRequest.model_validate(normalized)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Simulation request is invalid") from exc

    async def stream_local_preview_station_simulation(
        station_request: Request,
        station_simulation_request: SimulationRequest,
        station_claims: dict,
        access_policy: Optional[dict] = None,
    ):
        return await _stream_station_simulation(
            station_request,
            station_simulation_request,
            station_claims,
            access_policy,
            is_local_preview=True,
        )

    return await stream_authorized_simulation(
        req=simulation_request,
        request=request,
        claims=claims,
        enforce_fmu_claim=_enforce_fmu_claim,
        stream_station_simulation=stream_local_preview_station_simulation,
        get_effective_policy=_simulation_effective_access_policy,
    )


def _get_realtime_manager_for_route():
    return _runner_runtime.realtime_manager


_realtime_router = create_realtime_router(
    get_realtime_manager=_get_realtime_manager_for_route,
)


def _proxy_enforce_fmu_claim(claims: dict):
    return _enforce_fmu_claim(claims)


def _proxy_get_claim_lab_id(claims: dict):
    return _get_claim_lab_id(claims)


def _proxy_enforce_requested_reservation(claims: dict, requested: Optional[str]):
    return _enforce_requested_reservation(claims, requested)


def _proxy_allow_download(key: str):
    return _allow_proxy_download(key)


def _proxy_extract_authorization_header(request: Request):
    return _extract_authorization_header(request)


async def _proxy_issue_session_ticket(*args, **kwargs):
    return await _issue_session_ticket(*args, **kwargs)


async def _proxy_get_authorized_model_metadata(**kwargs):
    kwargs.setdefault("include_internal_variables", False)
    return await _runner_runtime.backend.get_authorized_model_metadata(**kwargs)


def _proxy_build_model_description_xml(metadata: dict):
    return _build_proxy_model_description_xml(metadata)


def _proxy_parse_fmi_major_version(value: Any):
    return _parse_fmi_major_version(value)


def _proxy_derive_gateway_ws_url(claims: dict):
    return _derive_gateway_ws_url(claims)


def _proxy_model_identifier(metadata: dict):
    return _proxy_model_identifier_impl(metadata)


def _proxy_model_identifier_for_route(metadata: dict):
    return _proxy_model_identifier(metadata)


def _proxy_collect_runtime_files(**kwargs):
    return _collect_runtime_files(**kwargs)


def _proxy_build_session_config(**kwargs):
    return _build_proxy_session_config(**kwargs)


def _proxy_normalize_ticket_id(session_ticket: Optional[str]):
    return _normalize_ticket_id(session_ticket)


def _proxy_build_artifact(**kwargs):
    return build_proxy_artifact(**kwargs)


def _proxy_build_artifact_headers(**kwargs):
    return build_proxy_artifact_headers(**kwargs)


_proxy_router = create_proxy_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_proxy_enforce_fmu_claim,
    get_claim_lab_id=_proxy_get_claim_lab_id,
    enforce_requested_reservation=_proxy_enforce_requested_reservation,
    allow_proxy_download=_proxy_allow_download,
    extract_authorization_header=_proxy_extract_authorization_header,
    new_request_id=lambda: f"proxy_{uuid4().hex[:8]}",
    issue_session_ticket=_proxy_issue_session_ticket,
    derive_gateway_ws_url=_proxy_derive_gateway_ws_url,
    get_authorized_model_metadata=_proxy_get_authorized_model_metadata,
    get_effective_policy=_simulation_effective_access_policy,
    get_authorized_parameter_sets=_catalog_get_authorized_parameter_sets,
    get_authorized_experiments=_catalog_get_authorized_experiments,
    build_proxy_model_description_xml=_proxy_build_model_description_xml,
    parse_fmi_major_version=_proxy_parse_fmi_major_version,
    proxy_model_identifier=_proxy_model_identifier_for_route,
    collect_runtime_files=_proxy_collect_runtime_files,
    build_proxy_session_config=_proxy_build_session_config,
    build_proxy_artifact=_proxy_build_artifact,
    build_proxy_artifact_headers=_proxy_build_artifact_headers,
    normalize_ticket_id=_proxy_normalize_ticket_id,
    get_signing_key=lambda: FMU_PROXY_SIGNING_KEY,
    logger=logger,
)


_run_router = create_run_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_enforce_fmu_claim,
    get_station_backend=lambda: _get_station_backend(),
    simulation_request_payload=_simulation_request_payload,
    extract_authorization_header=_extract_authorization_header,
    record_browser_session_started=lambda request, claims, sim_id: _record_browser_session_started(
        request, claims, sim_id
    ),
    new_simulation_id=lambda: uuid4().hex,
    get_effective_policy=_simulation_effective_access_policy,
    reject_unsupported_operation=_reject_unsupported_remote_operation,
)

_history_router = create_history_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_history_enforce_fmu_claim,
    reject_unsupported_operation=_history_reject_unsupported_remote_operation,
    get_station_backend=_get_scoped_station_backend,
    get_effective_policy=_simulation_effective_access_policy,
)


# ---------------------------------------------------------------------------
# Cancel a running simulation
# ---------------------------------------------------------------------------

_cancel_router = create_cancel_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_enforce_fmu_claim,
    reject_unsupported_operation=_reject_unsupported_remote_operation,
    get_station_backend=lambda: _get_scoped_station_backend("Simulation cancel endpoint"),
)


_stream_router = create_stream_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_enforce_fmu_claim,
    stream_station_simulation=_stream_station_simulation,
    get_effective_policy=_simulation_effective_access_policy,
)

_lifespan = create_lifespan(
    preload_jwks=_preload_jwks_if_enabled,
    get_realtime_manager=lambda: _runner_runtime.realtime_manager,
)


# Keep application creation and router registration in one composition seam;
# the injected callbacks above continue to preserve the historical patch points.
app = create_app(
    lifespan=_lifespan,
    routers=(
        _health_router,
        _catalog_router,
        _history_router,
        _aas_link_router,
        _aas_hints_router,
        _aas_sync_router,
        _aasx_router,
        _digital_twin_assets_router,
        _realtime_router,
        _proxy_router,
        _run_router,
        _cancel_router,
        _stream_router,
    ),
)

if _preview_tickets is not None:
    app.include_router(create_preview_router(
        _preview_tickets,
        FMU_LOCAL_EXECUTOR_INTERNAL_TOKEN,
        ensure_aas_policy=_ensure_local_preview_aas_policy,
        get_access_policy=_local_preview_access_payload,
        get_authorized_parameter_sets=_catalog_get_authorized_parameter_sets,
        get_authorized_experiments=_catalog_get_authorized_experiments,
        stream_simulation=_local_preview_stream_simulation,
    ))
