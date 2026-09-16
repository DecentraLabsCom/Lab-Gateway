"""
FMU Runner — FastAPI service for FMI Co-Simulation execution.

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
import tempfile
import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse
from pathlib import Path
from typing import Any, Optional
from concurrent.futures import ProcessPoolExecutor, Future
from uuid import uuid4

import httpx
import jwt
from fmpy import read_model_description
from fastapi import FastAPI, HTTPException, Depends, Query, WebSocket, Request
from fastapi.responses import StreamingResponse, Response
from starlette.datastructures import UploadFile
from xml.etree import ElementTree as ET

from auth import _fetch_jwks, verify_jwt, verify_jwt_token, jwks_health
from claim_values import (
    claim_reservation_key as _claim_reservation_key_value,
    coerce_epoch_seconds as _coerce_epoch_seconds_value,
    get_claim_lab_id as _get_claim_lab_id_value,
    normalize_lab_id as _normalize_lab_id_value,
)
from fmu_backend import LocalFmuBackend, StationFmuBackend
from backend_factory import build_fmu_backend as _build_fmu_backend_impl
from execution_adapters import (
    ensure_local_execution_backend as _ensure_local_execution_backend_adapter,
    simulation_request_payload as _simulation_request_payload_adapter,
)
from execution_lifecycle import (
    create_simulation_executor as _create_simulation_executor_impl,
    preload_jwks_if_enabled as _preload_jwks_if_enabled_impl,
    shutdown_simulation_executor as _shutdown_simulation_executor_impl,
    submit_simulation as _submit_simulation_impl,
)
from timeout_policy import effective_timeout_seconds as _effective_timeout_seconds_policy
from simulation_options import (
    SimulationOptions,
    SimulationOptionsError,
    parse_simulation_options as _parse_simulation_options_impl,
)
from simulation_model import resolve_fmi_type as _resolve_fmi_type_impl
from simulation_stream_payloads import (
    build_completed_event as _build_simulation_completed_event,
    iter_result_chunks as _iter_simulation_result_chunks,
)
from local_fmu_catalog import (
    _list_local_fmus_payload as _catalog_list_local_fmus_payload,
    _load_local_model_metadata as _catalog_load_local_model_metadata,
    _local_backend_health_payload as _catalog_local_backend_health_payload,
)
from metadata import (
    _collect_declared_type_definitions,
    _collect_variable_dimensions,
    _format_fmi3_binary_start_value,
    _format_fmi_start_value,
    _model_metadata_from_model_description,
    _normalize_metadata_value,
    _normalize_proxy_fmi3_type,
    _normalize_xml_value,
    _parse_fmi_major_version,
    _public_model_metadata,
)
from proxy_fmu import (
    _build_proxy_model_description_xml,
    _collect_runtime_files as _collect_proxy_runtime_files,
    _proxy_model_identifier as _proxy_model_identifier_impl,
    _validate_proxy_generation_supported,
)
from proxy_artifact import build_proxy_artifact, build_proxy_artifact_headers
from proxy_session_config import (
    build_proxy_session_config as _build_proxy_session_config_impl,
    derive_gateway_ws_url as _derive_gateway_ws_url_impl,
)
from simulation_history import (
    get_history_result as _get_history_result,
    init_history_db as _init_history_db,
    list_history as _list_history,
    save_history as _save_history_to_db,
)
from stream_errors import build_stream_error_payload as _build_stream_error_payload
from realtime_ws import RealtimeWsManager
from station_ws_proxy import StationRealtimeWsProxyManager
from realtime_factory import build_realtime_manager as _build_realtime_manager_impl
from proxy_rate_limiter import allow_download as _allow_proxy_download_impl
from temp_cleanup import cleanup_fmu_temp_files
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
from simulation_worker import run_simulation as _run_simulation
from simulation_request import SimulationRequest
from config import (
    _default_access_audit_url as _default_access_audit_url_value,
    _env_or_secret_file,
    _AAS_LINK_DATA_PATH,
    ACCESS_AUDIT_URL,
    AUTH_SESSION_TICKET_INTERNAL_TOKEN,
    AUTH_SESSION_TICKET_ISSUE_URL,
    AUTH_SESSION_TICKET_REDEEM_URL,
    FMU_BACKEND_MODE,
    FMU_DATA_PATH,
    FMU_LOCAL_DEV_MODE,
    FMU_LOCAL_REALTIME_ENABLED,
    FMU_PROXY_GATEWAY_WS_URL,
    FMU_PROXY_RUNTIME_PATH,
    FMU_PROXY_SIGNING_KEY,
    FMU_SESSION_OBSERVATION_MAX_ATTEMPTS,
    FMU_STATION_BASE_URL,
    FMU_STATION_INTERNAL_TOKEN,
    FMU_STATION_REQUEST_TIMEOUT,
    HISTORY_DB_PATH,
    INTERNAL_WS_TOKEN,
    MAX_CONCURRENT_PER_MODEL,
    MAX_SIMULATION_TIMEOUT,
    MAX_STOP_TIME,
    MIN_STEP_SIZE,
    PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE,
    SESSION_OBSERVER_GATEWAY_ID,
    SESSION_OBSERVER_SIGNING_SECRET,
    WS_ATTACH_GRACE_SECONDS,
    WS_CLEANUP_SECONDS,
    WS_CREATE_RATE_LIMIT_PER_MINUTE,
    WS_EXPIRING_NOTICE_SECONDS,
    WS_HEARTBEAT_SECONDS,
    WS_SESSION_QUEUE_SIZE,
)
from app_factory import create_app
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
from proxy_router import create_proxy_router

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

# ---------------------------------------------------------------------------
# Concurrency tracking
# ---------------------------------------------------------------------------

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


def _acquire_slot(lab_id: str):
    return _runner_runtime.acquire_slot(lab_id, MAX_CONCURRENT_PER_MODEL)


def _release_slot(lab_id: str):
    return _runner_runtime.release_slot(lab_id)


# ---------------------------------------------------------------------------
# Execution pool for simulations
# ---------------------------------------------------------------------------

def _create_executor():
    return _create_simulation_executor_impl(logger=logger)


_runner_runtime = create_fmu_runner_runtime(
    create_executor=lambda: None,
    history_db_path=HISTORY_DB_PATH,
)


async def _initialize_runtime():
    """Create process-bound resources only when the application starts."""
    if _runner_runtime.executor is None:
        _runner_runtime.executor = _create_executor()


def _track_running_future(
    sim_id: str,
    future: Future,
    lab_id: str,
    claims: dict,
    executor: Optional[ProcessPoolExecutor] = None,
):
    _runner_runtime.track_running_future(sim_id, future, lab_id, claims, executor)


def _get_running_entry(sim_id: str):
    return _runner_runtime.get_running_entry(sim_id)


def _shutdown_simulation_executor(executor: Any, *, force: bool = False) -> None:
    return _shutdown_simulation_executor_impl(executor, force=force)


def _submit_simulation(*args):
    return _submit_simulation_impl(
        _runner_runtime.executor,
        _run_simulation,
        _shutdown_simulation_executor,
        *args,
        process_pool_type=ProcessPoolExecutor,
        process_pool_factory=ProcessPoolExecutor,
    )


async def _preload_jwks_if_enabled():
    enabled = os.getenv("JWKS_PRELOAD_ON_STARTUP", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }
    return await _preload_jwks_if_enabled_impl(
        fetch_jwks=_fetch_jwks,
        enabled=enabled,
    )


def _finalize_simulation_tracking(sim_id: str, lab_id_fallback: Optional[str] = None):
    """Remove simulation from registry and release one concurrency slot."""
    lab_to_release = lab_id_fallback
    executor = None
    entry = _runner_runtime.pop_running_entry(sim_id)
    if entry is not None:
        _, lab_to_release, _, _, executor = entry
        _shutdown_simulation_executor(executor)
    if lab_to_release is not None:
        _release_slot(lab_to_release)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

async def _health_backend_payload():
    return await _runner_runtime.backend.health()


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


def _history_ensure_local_execution_backend(feature_name: str):
    return _ensure_local_execution_backend(feature_name)


def _history_get_claim_lab_id(claims: dict):
    return _get_claim_lab_id(claims)


def _history_normalize_lab_id(value):
    return _normalize_lab_id(value)


def _history_claim_reservation_key(claims: dict):
    return _claim_reservation_key(claims)


def _history_db_path():
    path = _runner_runtime.history_db_path
    if not path:
        raise RuntimeError("FMU history database path is not configured")
    return path


def _aas_link_path_for_router(access_key: str) -> Path:
    return _aas_link_path(access_key)


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
    from aas_generator import sync_fmu_to_basyx

    return await sync_fmu_to_basyx(**kwargs)


async def _aas_sync_runtime_status(lab_id: str):
    """Return bounded runner status to publish in the generated AAS."""
    health = dict(await _runner_runtime.backend.health())
    health["activeSimulationCount"] = _runner_runtime.registry.count_for_lab(lab_id)
    health["maxConcurrentSimulations"] = MAX_CONCURRENT_PER_MODEL
    return health


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
_history_router = create_history_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_history_enforce_fmu_claim,
    ensure_local_execution_backend=_history_ensure_local_execution_backend,
    get_claim_lab_id=_history_get_claim_lab_id,
    normalize_lab_id=_history_normalize_lab_id,
    claim_reservation_key=_history_claim_reservation_key,
    get_history_db_path=_history_db_path,
    list_history=_list_history,
    get_history_result=_get_history_result,
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
)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Simulation history persistence (SQLite)
# ---------------------------------------------------------------------------

async def _init_db():
    return await _init_history_db(_history_db_path())


async def _save_history(sim_id, lab_id, claims, fmu_filename, fmi_type, params, options, result, elapsed):
    return await _save_history_to_db(
        _history_db_path(),
        sim_id=sim_id,
        lab_id=lab_id,
        claims=claims,
        fmu_filename=fmu_filename,
        fmi_type=fmi_type,
        params=params,
        options=options,
        result=result,
        elapsed=elapsed,
        logger=logger,
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


def _effective_timeout_seconds(requested_timeout: int, claims: dict) -> int:
    return _effective_timeout_seconds_policy(
        requested_timeout,
        max_timeout=MAX_SIMULATION_TIMEOUT,
        exp_ts=_coerce_epoch_seconds(claims.get("exp")),
        now=time.time(),
    )


def _parse_simulation_options(options: dict, claims: dict) -> SimulationOptions:
    try:
        return _parse_simulation_options_impl(
            options,
            max_timeout=MAX_SIMULATION_TIMEOUT,
            max_stop_time=MAX_STOP_TIME,
            min_step_size=MIN_STEP_SIZE,
            effective_timeout_seconds=lambda requested: _effective_timeout_seconds(requested, claims),
        )
    except SimulationOptionsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_fmi_type(requested_type: Any, fmu_path: Path) -> Any:
    return _resolve_fmi_type_impl(
        requested_type,
        str(fmu_path),
        read_model_description,
    )


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


def _local_backend_health_payload() -> dict:
    return _catalog_local_backend_health_payload(
        data_path=FMU_DATA_PATH,
        executor=_runner_runtime.executor,
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
        station_base_url=FMU_STATION_BASE_URL,
        station_internal_token=FMU_STATION_INTERNAL_TOKEN,
        station_request_timeout=FMU_STATION_REQUEST_TIMEOUT,
        health_loader=_local_backend_health_payload,
        model_metadata_loader=_load_local_model_metadata,
        list_loader=_list_local_fmus_payload,
        logger=logger,
        station_backend_factory=StationFmuBackend,
        local_backend_factory=LocalFmuBackend,
    )


def _get_station_backend() -> StationFmuBackend:
    if isinstance(_runner_runtime.backend, StationFmuBackend):
        return _runner_runtime.backend
    raise HTTPException(status_code=500, detail="Active FMU backend is not station")


def _simulation_request_payload(req: SimulationRequest, sim_id: Optional[str] = None) -> dict:
    return _simulation_request_payload_adapter(
        reservation_key=req.reservationKey,
        lab_id=req.labId,
        parameters=req.parameters,
        options=req.options,
        sim_id=sim_id,
    )


def _ensure_local_execution_backend(feature_name: str):
    return _ensure_local_execution_backend_adapter(feature_name, _runner_runtime.backend)


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


def _stream_error_payload(exc: Exception, *, sim_id: Optional[str] = None) -> dict[str, Any]:
    return _build_stream_error_payload(exc, sim_id=sim_id)


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
            "Use FMU_BACKEND_MODE=station in production, or explicitly set "
            "FMU_BACKEND_MODE=local and FMU_LOCAL_DEV_MODE=true for isolated development."
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
    local_realtime_enabled=FMU_LOCAL_REALTIME_ENABLED,
    logger=logger,
    verify_jwt_token=verify_jwt_token,
    enforce_fmu_claim=_enforce_fmu_claim,
    resolve_fmu_path=_resolve_fmu_path,
    get_claim_lab_id=_get_claim_lab_id,
    normalize_lab_id=_normalize_lab_id,
    coerce_epoch_seconds=_coerce_epoch_seconds,
    acquire_slot=_acquire_slot,
    release_slot=_release_slot,
    redeem_session_ticket=_redeem_session_ticket,
    issue_session_ticket=_issue_session_ticket,
    confirm_session_started=_confirm_fmu_session_started,
    ws_session_queue_size=WS_SESSION_QUEUE_SIZE,
    ws_heartbeat_seconds=WS_HEARTBEAT_SECONDS,
    ws_expiring_notice_seconds=WS_EXPIRING_NOTICE_SECONDS,
    ws_attach_grace_seconds=WS_ATTACH_GRACE_SECONDS,
    ws_cleanup_seconds=WS_CLEANUP_SECONDS,
    internal_ws_token=INTERNAL_WS_TOKEN,
    ws_create_rate_limit_per_minute=WS_CREATE_RATE_LIMIT_PER_MINUTE,
    local_manager_factory=RealtimeWsManager,
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


def _run_enforce_fmu_claim(claims: dict):
    return _enforce_fmu_claim(claims)


def _run_backend_mode() -> str:
    return _runner_runtime.backend.mode


def _run_get_station_backend():
    return _get_station_backend()


def _run_simulation_request_payload(req: SimulationRequest, sim_id: Optional[str] = None):
    return _simulation_request_payload(req, sim_id)


def _run_extract_authorization_header(request: Request):
    return _extract_authorization_header(request)


async def _run_record_browser_session_started(*args, **kwargs):
    return await _record_browser_session_started(*args, **kwargs)


def _run_ensure_local_execution_backend(message: str):
    return _ensure_local_execution_backend(message)


def _run_get_claim_lab_id(claims: dict):
    return _get_claim_lab_id(claims)


def _run_normalize_lab_id(value):
    return _normalize_lab_id(value)


def _run_enforce_requested_reservation(claims: dict, requested: Optional[str]):
    return _enforce_requested_reservation(claims, requested)


def _run_resolve_fmu_path(fmu_filename: str):
    return _resolve_fmu_path(fmu_filename)


def _run_parse_simulation_options(options: dict, claims: dict):
    return _parse_simulation_options(options, claims)


def _run_resolve_fmi_type(fmi_type, fmu_path):
    return _resolve_fmi_type(fmi_type, fmu_path)


def _run_acquire_slot(lab_id: str):
    return _acquire_slot(lab_id)


def _run_new_simulation_id() -> str:
    return uuid4().hex


def _run_monotonic() -> float:
    return time.monotonic()


def _run_submit_simulation(*args):
    return _submit_simulation(*args)


def _run_track_running_future(*args, **kwargs):
    return _track_running_future(*args, **kwargs)


def _run_shutdown_executor(executor: Any, *, force: bool = False):
    return _shutdown_simulation_executor(executor, force=force)


def _run_finalize_tracking(*args, **kwargs):
    return _finalize_simulation_tracking(*args, **kwargs)


async def _run_save_history(*args, **kwargs):
    return await _save_history(*args, **kwargs)


async def _stream_station_simulation_for_route(*args, **kwargs):
    return await _stream_station_simulation(*args, **kwargs)


def _stream_iter_result_chunks(simulation_result):
    return _iter_simulation_result_chunks(simulation_result)


def _stream_build_completed_event(**kwargs):
    return _build_simulation_completed_event(**kwargs)


def _stream_error_payload_for_route(exc: Exception, *, sim_id: Optional[str] = None):
    return _stream_error_payload(exc, sim_id=sim_id)


async def _stream_sleep(seconds: float):
    await asyncio.sleep(seconds)


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
    enforce_fmu_claim=_run_enforce_fmu_claim,
    get_backend_mode=_run_backend_mode,
    get_station_backend=_run_get_station_backend,
    simulation_request_payload=_run_simulation_request_payload,
    extract_authorization_header=_run_extract_authorization_header,
    record_browser_session_started=_run_record_browser_session_started,
    ensure_local_execution_backend=_run_ensure_local_execution_backend,
    get_claim_lab_id=_run_get_claim_lab_id,
    normalize_lab_id=_run_normalize_lab_id,
    enforce_requested_reservation=_run_enforce_requested_reservation,
    resolve_fmu_path=_run_resolve_fmu_path,
    parse_simulation_options=_run_parse_simulation_options,
    resolve_fmi_type=_run_resolve_fmi_type,
    acquire_slot=_run_acquire_slot,
    new_simulation_id=_run_new_simulation_id,
    monotonic=_run_monotonic,
    submit_simulation=_run_submit_simulation,
    track_running_future=_run_track_running_future,
    shutdown_executor=_run_shutdown_executor,
    finalize_tracking=_run_finalize_tracking,
    save_history=_run_save_history,
    logger=logger,
)


# ---------------------------------------------------------------------------
# Cancel a running simulation
# ---------------------------------------------------------------------------

_cancel_router = create_cancel_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_enforce_fmu_claim,
    ensure_local_execution_backend=_ensure_local_execution_backend,
    get_running_entry=_get_running_entry,
    get_claim_lab_id=_get_claim_lab_id,
    normalize_lab_id=_normalize_lab_id,
    claim_reservation_key=_claim_reservation_key,
    shutdown_executor=_shutdown_simulation_executor,
    finalize_tracking=_finalize_simulation_tracking,
)


_stream_router = create_stream_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_run_enforce_fmu_claim,
    get_backend_mode=_run_backend_mode,
    stream_station_simulation=_stream_station_simulation_for_route,
    ensure_local_execution_backend=_run_ensure_local_execution_backend,
    get_claim_lab_id=_run_get_claim_lab_id,
    normalize_lab_id=_run_normalize_lab_id,
    enforce_requested_reservation=_run_enforce_requested_reservation,
    resolve_fmu_path=_run_resolve_fmu_path,
    parse_simulation_options=_run_parse_simulation_options,
    resolve_fmi_type=_run_resolve_fmi_type,
    new_simulation_id=_run_new_simulation_id,
    monotonic=_run_monotonic,
    acquire_slot=_run_acquire_slot,
    record_browser_session_started=_run_record_browser_session_started,
    submit_simulation=_run_submit_simulation,
    track_running_future=_run_track_running_future,
    shutdown_executor=_run_shutdown_executor,
    finalize_tracking=_run_finalize_tracking,
    iter_result_chunks=_stream_iter_result_chunks,
    build_completed_event=_stream_build_completed_event,
    stream_error_payload=_stream_error_payload_for_route,
    save_history=_run_save_history,
    sleep=_stream_sleep,
    logger=logger,
)

# ---------------------------------------------------------------------------
# Temp file cleanup (FMPy extracts FMUs to tempdir)
# ---------------------------------------------------------------------------

async def _cleanup_temp_files():
    """Best-effort cleanup of FMPy temp dirs on shutdown."""
    removed = cleanup_fmu_temp_files(Path(tempfile.gettempdir()))
    if removed:
        logger.info("Cleaned up %d FMPy temp directories", removed)


_lifespan = create_lifespan(
    initialize_runtime=_initialize_runtime,
    init_db=_init_db,
    preload_jwks=_preload_jwks_if_enabled,
    get_realtime_manager=lambda: _runner_runtime.realtime_manager,
    get_executor=lambda: _runner_runtime.executor,
    shutdown_executor=_shutdown_simulation_executor,
    cleanup_temp_files=_cleanup_temp_files,
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
        _realtime_router,
        _proxy_router,
        _run_router,
        _cancel_router,
        _stream_router,
    ),
)
