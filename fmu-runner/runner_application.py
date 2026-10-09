"""
FMU Runner — FastAPI facade for remote FMI simulation services.

Endpoints:
  POST /api/v1/simulations/run      — Execute a simulation
  GET  /api/v1/simulations/describe — Describe FMU model metadata
  GET  /health                      — Health check
"""

import base64
import os
import time
import json
import logging
import asyncio
import re
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import httpx
import jwt
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
from runner_runtime import create_fmu_runner_runtime
from simulation_request import SimulationRequest
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
from stream_router import create_stream_router
from realtime_router import create_realtime_router
from aas_link_router import create_aas_link_router
from aas_hints_router import create_aas_hints_router
from aas_sync_router import create_aas_sync_router
from aasx_router import create_aasx_router
from aasx_catalog import AasxPackageCatalog
from aas_association_service import AasAssociationService
from proxy_router import create_proxy_router

FMU_DATA_PATH = CONFIG.fmu_data_path
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
FMU_BACKEND_MODE = CONFIG.fmu_backend_mode
FMU_LOCAL_DEV_MODE = CONFIG.fmu_local_dev_mode
FMU_LOCAL_EXECUTOR_BASE_URL = CONFIG.fmu_local_executor_base_url
FMU_LOCAL_EXECUTOR_INTERNAL_TOKEN = CONFIG.fmu_local_executor_internal_token
FMU_STATION_BASE_URL = CONFIG.fmu_station_base_url
FMU_STATION_INTERNAL_TOKEN = CONFIG.fmu_station_internal_token
FMU_STATION_REQUEST_TIMEOUT = CONFIG.fmu_station_request_timeout
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


async def _catalog_get_authorized_model_metadata(*, claims: dict, requested_fmu_filename: Optional[str] = None):
    return await _runner_runtime.backend.get_authorized_model_metadata(
        claims=claims,
        requested_fmu_filename=requested_fmu_filename,
    )


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


def _aas_sync_resolve_fmu_path(access_key: str):
    return _resolve_fmu_path(access_key)


def _aas_sync_read_model_description(fmu_path):
    return read_model_description(str(fmu_path))


def _aas_sync_metadata_builder(model_description):
    return _model_metadata_from_model_description(model_description)


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
    public_model_metadata=_catalog_public_model_metadata,
    list_authorized_fmu=_catalog_list_authorized_fmu,
)
_aas_link_router = create_aas_link_router(get_link_path=_aas_link_path_for_router)
_aas_hints_router = create_aas_hints_router(
    resolve_fmu_path=_aas_hints_resolve_fmu_path,
    read_model_description=_aas_hints_read_model_description,
    normalize_xml_value=_normalize_xml_value,
    logger=logger,
)
_aas_sync_router = create_aas_sync_router(
    resolve_fmu_path=_aas_sync_resolve_fmu_path,
    read_model_description=_aas_sync_read_model_description,
    metadata_builder=_aas_sync_metadata_builder,
    sync_fmu_to_basyx=_aas_sync_to_basyx,
    get_runtime_status=_aas_sync_runtime_status,
    logger=logger,
    record_aasx=_record_aasx_association,
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


# ----- helpers -----

def _is_within_base(base: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


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
    """Search *FMU_DATA_PATH* for a .fmu file matching *fmu_filename*."""
    fmu_filename = _validate_storage_key(fmu_filename, "FMU filename")
    if not fmu_filename.lower().endswith(".fmu"):
        raise HTTPException(status_code=400, detail="Only .fmu files are accepted")
    base = Path(FMU_DATA_PATH).resolve()
    if not base.is_dir():
        raise HTTPException(status_code=503, detail="FMU data directory is unavailable")

    def _trusted_match(directory: Path) -> Optional[Path]:
        """Return a matching file already discovered under the trusted root."""
        try:
            entries = directory.iterdir()
        except OSError:
            return None
        for entry in entries:
            # Compare against the directory entry name; never construct a path
            # by appending the request value to a filesystem path.
            if os.path.normcase(entry.name) != os.path.normcase(fmu_filename):
                continue
            try:
                resolved = entry.resolve(strict=True)
            except OSError:
                continue
            if _is_within_base(base, resolved) and resolved.is_file():
                return resolved
        return None

    # Direct match.  The path comes from directory enumeration, not user input.
    direct = _trusted_match(base)
    if direct is not None:
        return direct

    # Search in provider sub-directories (fmu-data/<provider-wallet>/file.fmu).
    for child in base.iterdir():
        if child.is_dir():
            candidate = _trusted_match(child)
            if candidate is not None:
                return candidate
    raise HTTPException(status_code=404, detail=f"FMU file not found: {fmu_filename}")


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
    time_mode: str = "simtime",
) -> dict[str, Any]:
    return _build_proxy_session_config_impl(
        fmi_version=fmi_version,
        gateway_ws_url=gateway_ws_url,
        lab_id=lab_id,
        reservation_key=reservation_key,
        session_ticket=session_ticket,
        ticket_expires_at=ticket_expires_at,
        time_mode=time_mode,
    )


def _local_metadata_backend_health_payload(lab_id: Optional[str] = None) -> dict:
    del lab_id
    return _catalog_local_metadata_backend_health_payload(
        data_path=FMU_DATA_PATH,
    )


def _load_local_model_metadata(fmu_filename: str) -> dict:
    return _catalog_load_local_model_metadata(
        fmu_filename,
        resolve_fmu_path=_resolve_fmu_path,
        model_description_reader=read_model_description,
        model_metadata_builder=_model_metadata_from_model_description,
        logger=logger,
    )


def _list_local_fmus_payload(claimed_file: str) -> dict:
    return _catalog_list_local_fmus_payload(
        claimed_file,
        data_path=FMU_DATA_PATH,
        resolve_fmu_path=_resolve_fmu_path,
        is_within_base=_is_within_base,
    )


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
        sim_id=sim_id,
    )


def _reject_unsupported_remote_operation(feature_name: str):
    return _reject_unsupported_remote_operation_adapter(feature_name, _runner_runtime.backend.mode)


def _get_scoped_station_backend(feature_name: str) -> StationFmuBackend:
    if isinstance(_runner_runtime.backend, StationFmuBackend):
        return _runner_runtime.backend
    _reject_unsupported_remote_operation(feature_name)


async def _stream_station_simulation(request: Request, req: SimulationRequest, claims: dict):
    station_backend = _get_station_backend()
    authorization = _extract_authorization_header(request)
    station_backend.build_authorized_context(
        claims=claims,
        requested_lab_id=req.labId,
        requested_reservation_key=req.reservationKey,
    )
    sim_id = uuid4().hex
    # The gateway records the accepted job before releasing it to the Station.
    # A failed Station call is therefore an accepted-but-not-released job, not
    # work that ran without durable evidence.
    await _record_browser_session_started(request, claims, sim_id)
    client, response = await station_backend.open_authorized_simulation_stream(
        claims=claims,
        request_payload=_simulation_request_payload(req, sim_id),
        authorization=authorization,
    )
    media_type = response.headers.get("content-type") or "application/x-ndjson"

    async def _forward_stream():
        try:
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk
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
    if not SESSION_OBSERVER_GATEWAY_ID or not SESSION_OBSERVER_SIGNING_SECRET:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SESSION_OBSERVER_NOT_CONFIGURED",
                "error": "Session observer gateway credentials are not configured",
            },
        )
    try:
        padding = "=" * (-len(SESSION_OBSERVER_SIGNING_SECRET) % 4)
        signing_key = base64.urlsafe_b64decode(SESSION_OBSERVER_SIGNING_SECRET + padding)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "SESSION_OBSERVER_NOT_CONFIGURED", "error": "Invalid session observer signing secret"},
        ) from exc
    if len(signing_key) < 32:
        raise HTTPException(
            status_code=503,
            detail={"code": "SESSION_OBSERVER_NOT_CONFIGURED", "error": "Session observer signing secret is too short"},
        )
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": SESSION_OBSERVER_GATEWAY_ID,
            "sub": SESSION_OBSERVER_GATEWAY_ID,
            "aud": "session-observation",
            "scope": "session-observation:submit",
            "iat": now,
            "exp": now + 60,
            "jti": base64.urlsafe_b64encode(os.urandom(18)).rstrip(b"=").decode("ascii"),
        },
        signing_key,
        algorithm="HS256",
    )
    return f"Bearer {token}"


async def _confirm_fmu_session_started(
    *,
    session_ticket: str,
    claims: dict,
    session_id: str,
    reservation_key: Optional[str] = None,
    request_id: Optional[str] = None,
) -> bool:
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
    reject_unsupported_operation=_reject_unsupported_remote_operation,
)

_history_router = create_history_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_history_enforce_fmu_claim,
    reject_unsupported_operation=_history_reject_unsupported_remote_operation,
    get_station_backend=_get_scoped_station_backend,
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
        _realtime_router,
        _proxy_router,
        _run_router,
        _cancel_router,
        _stream_router,
    ),
)
