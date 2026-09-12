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
from contextlib import asynccontextmanager
try:
    import resource as posix_resource
except ImportError:
    posix_resource = None  # Not available on Windows
from pathlib import Path
from typing import Any, Optional, cast
from concurrent.futures import ProcessPoolExecutor, Future
from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4

import httpx
import jwt
from fmpy import read_model_description, simulate_fmu
from fastapi import FastAPI, HTTPException, Depends, Query, WebSocket, Request
from fastapi.responses import StreamingResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, field_validator
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
from execution_slots import ConcurrencySlots
from execution_tracking import SimulationRegistry
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
from health_router import create_health_router
from catalog_router import create_catalog_router
from history_router import create_history_router
from aas_link_router import create_aas_link_router
from aas_hints_router import create_aas_hints_router
from aas_sync_router import create_aas_sync_router
from proxy_router import create_proxy_router

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _env_or_secret_file(name: str, default: str = "") -> str:
    """Read a value from the environment, falling back to a mounted secret."""
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
        logging.warning("Unable to read secret file for %s", name)
        return default


FMU_DATA_PATH = os.getenv("FMU_DATA_PATH", "/app/fmu-data")
# Writable store for AAS link override files (separate from read-only fmu-data).
_AAS_LINK_DATA_PATH = Path(os.getenv("AAS_LINK_DATA_PATH", "/app/data/aas-links"))
MAX_SIMULATION_TIMEOUT = int(os.getenv("MAX_SIMULATION_TIMEOUT", "300"))
MAX_CONCURRENT_PER_MODEL = int(os.getenv("MAX_CONCURRENT_PER_MODEL", "10"))
# Keep the virtual address-space ceiling above the container memory ceiling.
# FMPy/Numpy can reserve substantial virtual address space before dlopen() maps
# the FMU binary; the Docker cgroup remains the effective resident-memory cap.
FMU_WORKER_ADDRESS_SPACE_LIMIT = int(os.getenv(
    "FMU_WORKER_ADDRESS_SPACE_LIMIT",
    str(2 * 1024 ** 3),
))
MAX_STOP_TIME = float(os.getenv("MAX_STOP_TIME", "86400"))  # 24h upper bound
MIN_STEP_SIZE = float(os.getenv("MIN_STEP_SIZE", "1e-6"))    # 1 µs lower bound
HISTORY_DB_PATH = os.getenv("HISTORY_DB_PATH", "/app/data/history.db")
WS_SESSION_QUEUE_SIZE = int(os.getenv("WS_SESSION_QUEUE_SIZE", "64"))
WS_HEARTBEAT_SECONDS = float(os.getenv("WS_HEARTBEAT_SECONDS", "15"))
WS_EXPIRING_NOTICE_SECONDS = int(os.getenv("WS_EXPIRING_NOTICE_SECONDS", "60"))
WS_ATTACH_GRACE_SECONDS = int(os.getenv("WS_ATTACH_GRACE_SECONDS", "120"))
WS_CLEANUP_SECONDS = float(os.getenv("WS_CLEANUP_SECONDS", "15"))
INTERNAL_WS_TOKEN = _env_or_secret_file("FMU_INTERNAL_WS_TOKEN")
AUTH_SESSION_TICKET_ISSUE_URL = os.getenv(
    "AUTH_SESSION_TICKET_ISSUE_URL",
    "http://blockchain-services:8080/auth/fmu/session-ticket/issue",
)
AUTH_SESSION_TICKET_REDEEM_URL = os.getenv(
    "AUTH_SESSION_TICKET_REDEEM_URL",
    "http://blockchain-services:8080/auth/fmu/session-ticket/redeem",
)
AUTH_SESSION_TICKET_INTERNAL_TOKEN = _env_or_secret_file("AUTH_SESSION_TICKET_INTERNAL_TOKEN")
SESSION_OBSERVER_GATEWAY_ID = os.getenv("SESSION_OBSERVER_GATEWAY_ID", "").strip().lower()
SESSION_OBSERVER_SIGNING_SECRET = _env_or_secret_file("SESSION_OBSERVER_SIGNING_SECRET").strip()


def _default_access_audit_url() -> str:
    redeem_url = urlparse(AUTH_SESSION_TICKET_REDEEM_URL)
    if not redeem_url.scheme or not redeem_url.netloc:
        return ""
    return urlunparse(redeem_url._replace(
        path="/access-audit/internal/session-observed",
        params="",
        query="",
        fragment="",
    ))


ACCESS_AUDIT_URL = os.getenv("ACCESS_AUDIT_URL", "").strip() or _default_access_audit_url()
FMU_PROXY_RUNTIME_PATH = os.getenv("FMU_PROXY_RUNTIME_PATH", "/app/fmu-proxy-runtime")
FMU_PROXY_GATEWAY_WS_URL = os.getenv("FMU_PROXY_GATEWAY_WS_URL", "")
FMU_PROXY_SIGNING_KEY = _env_or_secret_file("FMU_PROXY_SIGNING_KEY")
FMU_BACKEND_MODE = os.getenv("FMU_BACKEND_MODE", "station").strip().lower()
FMU_LOCAL_DEV_MODE = os.getenv("FMU_LOCAL_DEV_MODE", "false").strip().lower() in (
    "1", "true", "yes", "on",
)
FMU_LOCAL_REALTIME_ENABLED = os.getenv("FMU_LOCAL_REALTIME_ENABLED", "false").strip().lower() in (
    "1", "true", "yes", "on",
)
FMU_STATION_BASE_URL = os.getenv("FMU_STATION_BASE_URL", "").strip()
FMU_STATION_INTERNAL_TOKEN = _env_or_secret_file("FMU_STATION_INTERNAL_TOKEN").strip()
FMU_STATION_REQUEST_TIMEOUT = float(os.getenv("FMU_STATION_REQUEST_TIMEOUT", "10"))
FMU_SESSION_OBSERVATION_MAX_ATTEMPTS = max(
    1, int(os.getenv("FMU_SESSION_OBSERVATION_MAX_ATTEMPTS", "3"))
)
PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE = int(os.getenv("PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE", "20"))
WS_CREATE_RATE_LIMIT_PER_MINUTE = int(os.getenv("WS_CREATE_RATE_LIMIT_PER_MINUTE", "30"))

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

_active_slots = ConcurrencySlots()
_active_counts = _active_slots.counts
_active_lock = _active_slots.lock

_proxy_download_hits: dict[str, deque[float]] = defaultdict(deque)
_proxy_download_lock = Lock()
_browser_observed_credentials: set[str] = set()
_browser_observation_lock = Lock()


def _normalize_ticket_id(session_ticket: Optional[str]) -> Optional[str]:
    return _normalize_ticket_id_value(session_ticket)


def _allow_proxy_download(key: str) -> bool:
    if PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE <= 0:
        return False
    now = time.time()
    with _proxy_download_lock:
        bucket = _proxy_download_hits[key]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE:
            return False
        bucket.append(now)
        return True


def _acquire_slot(lab_id: str):
    return _active_slots.acquire(lab_id, MAX_CONCURRENT_PER_MODEL)


def _release_slot(lab_id: str):
    return _active_slots.release(lab_id)


# ---------------------------------------------------------------------------
# Execution pool for simulations
# ---------------------------------------------------------------------------

def _create_executor():
    return _create_simulation_executor_impl(logger=logger)


_executor = _create_executor()

# ---------------------------------------------------------------------------
# Running-simulation registry (for cancellation)
# ---------------------------------------------------------------------------

_running_registry = SimulationRegistry()
_running_futures = _running_registry.entries
_running_lock = _running_registry.lock


def _track_running_future(
    sim_id: str,
    future: Future,
    lab_id: str,
    claims: dict,
    executor: Optional[ProcessPoolExecutor] = None,
):
    _running_registry.register(sim_id, future, lab_id, claims, executor)


def _shutdown_simulation_executor(executor: Any, *, force: bool = False) -> None:
    return _shutdown_simulation_executor_impl(executor, force=force)


def _submit_simulation(*args):
    return _submit_simulation_impl(
        _executor,
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
    entry = _running_registry.pop(sim_id)
    if entry is not None:
        _, lab_to_release, _, _, executor = entry
        _shutdown_simulation_executor(executor)
    if lab_to_release is not None:
        _release_slot(lab_to_release)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await _init_db()
    await _preload_jwks_if_enabled()
    if _realtime_manager is not None:
        await _realtime_manager.start()
    try:
        yield
    finally:
        if _realtime_manager is not None:
            await _realtime_manager.stop()
        _shutdown_simulation_executor(_executor)
        await _cleanup_temp_files()


async def _health_backend_payload():
    return await _fmu_backend.health()


async def _refresh_health_jwks():
    return await _fetch_jwks()


def _health_auth_status():
    return jwks_health()


def _catalog_enforce_fmu_claim(claims: dict, *, allow_provider_describe: bool = False):
    return _enforce_fmu_claim(claims, allow_provider_describe=allow_provider_describe)


async def _catalog_get_authorized_model_metadata(*, claims: dict, requested_fmu_filename: Optional[str] = None):
    return await _fmu_backend.get_authorized_model_metadata(
        claims=claims,
        requested_fmu_filename=requested_fmu_filename,
    )


def _catalog_public_model_metadata(metadata: dict):
    return _public_model_metadata(metadata)


async def _catalog_list_authorized_fmu(*, claims: dict):
    return await _fmu_backend.list_authorized_fmu(claims=claims)


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
    return HISTORY_DB_PATH


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


app = FastAPI(title="FMU Runner", version="0.2.0", lifespan=_lifespan)
app.include_router(create_health_router(
    backend_health=_health_backend_payload,
    refresh_jwks=_refresh_health_jwks,
    auth_health=_health_auth_status,
))
app.include_router(create_catalog_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_catalog_enforce_fmu_claim,
    get_authorized_model_metadata=_catalog_get_authorized_model_metadata,
    public_model_metadata=_catalog_public_model_metadata,
    list_authorized_fmu=_catalog_list_authorized_fmu,
))
app.include_router(create_history_router(
    verify_jwt=verify_jwt,
    enforce_fmu_claim=_history_enforce_fmu_claim,
    ensure_local_execution_backend=_history_ensure_local_execution_backend,
    get_claim_lab_id=_history_get_claim_lab_id,
    normalize_lab_id=_history_normalize_lab_id,
    claim_reservation_key=_history_claim_reservation_key,
    get_history_db_path=_history_db_path,
    list_history=_list_history,
    get_history_result=_get_history_result,
))
app.include_router(create_aas_link_router(get_link_path=_aas_link_path_for_router))
app.include_router(create_aas_hints_router(
    resolve_fmu_path=_aas_hints_resolve_fmu_path,
    read_model_description=_aas_hints_read_model_description,
    normalize_xml_value=_normalize_xml_value,
    logger=logger,
))
app.include_router(create_aas_sync_router(
    resolve_fmu_path=_aas_sync_resolve_fmu_path,
    read_model_description=_aas_sync_read_model_description,
    metadata_builder=_aas_sync_metadata_builder,
    sync_fmu_to_basyx=_aas_sync_to_basyx,
    logger=logger,
))


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Simulation history persistence (SQLite)
# ---------------------------------------------------------------------------

async def _init_db():
    return await _init_history_db(HISTORY_DB_PATH)


async def _save_history(sim_id, lab_id, claims, fmu_filename, fmi_type, params, options, result, elapsed):
    return await _save_history_to_db(
        HISTORY_DB_PATH,
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


# ----- models -----

class SimulationRequest(BaseModel):
    reservationKey: Optional[str] = None
    labId: Optional[str] = None
    parameters: dict = Field(default_factory=dict)
    options: dict = Field(default_factory=dict)

    @field_validator("labId", mode="before")
    @classmethod
    def _normalize_lab_id(cls, value):
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return str(value)
        return value


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
        executor=_executor,
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
    if FMU_BACKEND_MODE == "station":
        logger.info("FMU backend mode selected: station")
        return StationFmuBackend(
            base_url=FMU_STATION_BASE_URL,
            internal_token=FMU_STATION_INTERNAL_TOKEN,
            request_timeout=FMU_STATION_REQUEST_TIMEOUT,
        )

    if FMU_BACKEND_MODE != "local":
        logger.error(
            "Unknown FMU_BACKEND_MODE=%s; local execution remains disabled",
            FMU_BACKEND_MODE,
        )

    if FMU_BACKEND_MODE == "local" and not FMU_LOCAL_DEV_MODE:
        logger.error(
            "FMU_BACKEND_MODE=local requires FMU_LOCAL_DEV_MODE=true; "
            "native FMU execution is disabled",
        )

    logger.info("FMU backend mode selected: local")
    return LocalFmuBackend(
        health_loader=_local_backend_health_payload,
        model_metadata_loader=_load_local_model_metadata,
        list_loader=_list_local_fmus_payload,
        allow_execution=FMU_BACKEND_MODE == "local" and FMU_LOCAL_DEV_MODE,
    )


def _get_station_backend() -> StationFmuBackend:
    if isinstance(_fmu_backend, StationFmuBackend):
        return _fmu_backend
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
    return _ensure_local_execution_backend_adapter(feature_name, _fmu_backend)


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
        observation_lock=_browser_observation_lock,
        observed_credentials=_browser_observed_credentials,
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


_fmu_backend = _build_fmu_backend()


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
            f"Realtime FMU sessions are not wired for FMU_BACKEND_MODE={_fmu_backend.mode}. "
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


if _fmu_backend.supports_local_execution and FMU_LOCAL_REALTIME_ENABLED:
    _realtime_manager = RealtimeWsManager(
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
    )
elif _fmu_backend.mode == "station":
    _realtime_manager = StationRealtimeWsProxyManager(
        logger=logger,
        station_backend=_fmu_backend,
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
    )
else:
    _realtime_manager = _UnsupportedRealtimeManager(
        reason=(
            "Local realtime FMU execution is disabled by default because native "
            "doStep calls cannot be force-terminated inside the ASGI process. "
            "Use FMU_BACKEND_MODE=station in production, or explicitly set "
            "FMU_LOCAL_REALTIME_ENABLED=true only for isolated development."
        )
        if _fmu_backend.supports_local_execution
        else None
    )


def _run_simulation(fmu_path: str, start_time: float, stop_time: float, step_size: float,
                    start_values: dict, timeout: int, fmi_type: str = "CoSimulation",
                    solver_name: str = "Euler"):
    """Execute simulation in a subprocess (called via ProcessPoolExecutor).

    Returns dict with keys: time, outputs, outputVariables.
    Supports both CoSimulation and ModelExchange FMU types.
    """
    # Apply resource limits inside the worker process (Linux only)
    try:
        if posix_resource is not None:
            resource_api = cast(Any, posix_resource)
            resource_api.setrlimit(resource_api.RLIMIT_CPU, (timeout, timeout + 5))
            resource_api.setrlimit(
                resource_api.RLIMIT_AS,
                (FMU_WORKER_ADDRESS_SPACE_LIMIT, FMU_WORKER_ADDRESS_SPACE_LIMIT),
            )
    except Exception:
        pass  # May fail on non-Linux or if not root

    sim_kwargs: dict[str, Any] = dict(
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        start_values=start_values,
        fmi_type=fmi_type,
    )
    # For ModelExchange, FMPy provides an ODE solver (default: Euler; optional: CVode)
    if fmi_type == "ModelExchange":
        sim_kwargs["solver"] = solver_name

    result = simulate_fmu(fmu_path, **sim_kwargs)

    # result is a numpy structured array
    column_names = result.dtype.names
    if column_names is None:
        raise RuntimeError("FMU simulation returned no named result columns")
    col_names = list(column_names)
    outputs = {}
    time_col = None
    for name in col_names:
        arr = result[name].tolist()
        if name.lower() == "time":
            time_col = arr
        else:
            outputs[name] = arr

    return {
        "time": time_col or [],
        "outputs": outputs,
        "outputVariables": list(outputs.keys()),
    }


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


@app.websocket("/api/v1/fmu/sessions")
async def fmu_realtime_sessions(websocket: WebSocket):
    await _realtime_manager.handle_websocket(websocket, internal=False)


@app.websocket("/internal/fmu/sessions")
async def fmu_realtime_sessions_internal(websocket: WebSocket):
    await _realtime_manager.handle_websocket(websocket, internal=True)


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
    return await _fmu_backend.get_authorized_model_metadata(**kwargs)


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
# Keep the historical private symbol available to callers and tests while the
# registered endpoint lives in the dedicated router.
download_proxy_fmu = cast(APIRoute, _proxy_router.routes[0]).endpoint
app.include_router(_proxy_router)


@app.post("/api/v1/simulations/run")
async def run_simulation(
    req: SimulationRequest,
    request: Request,
    claims: dict = Depends(verify_jwt),
):
    """Execute an FMU simulation and return results.

    Supports CoSimulation and ModelExchange. Auto-detects FMI type from
    model description when ``options.fmiType`` is absent.
    """
    _enforce_fmu_claim(claims)
    if _fmu_backend.mode == "station":
        station_backend = _get_station_backend()
        station_backend.build_authorized_context(
            claims=claims,
            requested_lab_id=req.labId,
            requested_reservation_key=req.reservationKey,
        )
        sim_id = uuid4().hex
        await _record_browser_session_started(request, claims, sim_id)
        result = await station_backend.run_authorized_simulation(
            claims=claims,
            request_payload=_simulation_request_payload(req, sim_id),
            authorization=_extract_authorization_header(request),
        )
        if isinstance(result, dict):
            result = dict(result)
            # The gateway id is the durable observation key. Ignore any
            # executor identifier returned by Station so evidence stays tied
            # to the gateway request.
            result["simId"] = sim_id
        return result
    _ensure_local_execution_backend("Simulation run endpoint")

    # Determine FMU filename from JWT claims or request
    fmu_filename = claims.get("accessKey") or claims.get("fmuFileName")
    claims_lab_id = _get_claim_lab_id(claims)
    request_lab_id = _normalize_lab_id(req.labId)
    if claims_lab_id and request_lab_id and claims_lab_id != request_lab_id:
        raise HTTPException(status_code=403, detail="JWT not authorised for requested labId")
    lab_id = request_lab_id or claims_lab_id or "unknown"
    _enforce_requested_reservation(claims, req.reservationKey)

    if req.labId is None and claims_lab_id:
        req.labId = claims_lab_id

    if not fmu_filename:
        raise HTTPException(status_code=400, detail="Cannot determine FMU file name from JWT or request")

    fmu_path = _resolve_fmu_path(fmu_filename)

    execution_options = _parse_simulation_options(req.options, claims)
    start_time = execution_options.start_time
    stop_time = execution_options.stop_time
    step_size = execution_options.step_size
    timeout = execution_options.timeout

    # --- FMI type auto-detection ---
    fmi_type = _resolve_fmi_type(execution_options.fmi_type, fmu_path)
    solver_name = execution_options.solver_name

    # Concurrency check
    _acquire_slot(lab_id)

    sim_id = uuid4().hex
    t0 = time.monotonic()
    future: Optional[Future] = None
    job_executor: Any = None
    try:
        # Durable observation is the acceptance gate. The executor is not
        # released until it succeeds, so a failed observation cannot race with
        # work that has already started.
        await _record_browser_session_started(request, claims, sim_id)
        job_executor, future = _submit_simulation(
            str(fmu_path),
            start_time,
            stop_time,
            step_size,
            req.parameters,
            timeout,
            fmi_type,
            solver_name,
        )
        if future is None:
            raise RuntimeError("simulation executor returned no future")
        _track_running_future(sim_id, future, lab_id, claims, job_executor)
        try:
            sim_result = await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout)
        except asyncio.TimeoutError as exc:
            if not future.done():
                future.cancel()
            # Future.cancel() cannot stop a process that already entered FMPy.
            # Kill this simulation's private worker and release its slot now.
            _shutdown_simulation_executor(job_executor, force=True)
            raise HTTPException(status_code=504, detail="Simulation timed out") from exc
    except HTTPException:
        raise
    except Exception as exc:
        if future is None and job_executor is not None:
            _shutdown_simulation_executor(job_executor, force=True)
        logger.error(
            "Simulation failed for lab %s: %s",
            str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="Simulation failed") from exc
    finally:
        _finalize_simulation_tracking(sim_id, lab_id)

    elapsed = round(time.monotonic() - t0, 3)
    logger.info(
        "Simulation completed for lab %s in %.3fs",
        str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
        elapsed,
    )

    # Persist to history DB
    await _save_history(sim_id, lab_id, claims, fmu_filename, fmi_type,
                        req.parameters, req.options, sim_result, elapsed)

    return {
        "status": "completed",
        "simId": sim_id,
        "simulationTime": elapsed,
        "fmiType": fmi_type,
        **sim_result,
    }


# ---------------------------------------------------------------------------
# Cancel a running simulation
# ---------------------------------------------------------------------------

@app.post("/api/v1/simulations/{sim_id}/cancel")
async def cancel_simulation(sim_id: str, claims: dict = Depends(verify_jwt)):
    """Attempt to cancel a running simulation by its ID."""
    _enforce_fmu_claim(claims)
    _ensure_local_execution_backend("Simulation cancel endpoint")
    with _running_lock:
        entry = _running_futures.get(sim_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Simulation not found or already finished")
    future, lab_id, reservation_key, puc_hash, job_executor = entry
    if _get_claim_lab_id(claims) != _normalize_lab_id(lab_id):
        raise HTTPException(status_code=403, detail="Token is not authorised for requested simulation")
    if _claim_reservation_key(claims) != reservation_key:
        raise HTTPException(status_code=403, detail="Token is not authorised for requested simulation")
    if str(claims.get("pucHash") or "").strip().lower() != puc_hash:
        raise HTTPException(status_code=403, detail="Token is not authorised for requested simulation")
    future.cancel()
    _shutdown_simulation_executor(job_executor, force=True)
    _finalize_simulation_tracking(sim_id)
    return {"status": "cancelled"}

# ---------------------------------------------------------------------------
# Temp file cleanup (FMPy extracts FMUs to tempdir)
# ---------------------------------------------------------------------------

async def _cleanup_temp_files():
    """Best-effort cleanup of FMPy temp dirs on shutdown."""
    removed = cleanup_fmu_temp_files(Path(tempfile.gettempdir()))
    if removed:
        logger.info("Cleaned up %d FMPy temp directories", removed)


# ---------------------------------------------------------------------------
# NDJSON Streaming endpoint
# ---------------------------------------------------------------------------

@app.post("/api/v1/simulations/stream")
async def stream_simulation(
    req: SimulationRequest,
    request: Request,
    claims: dict = Depends(verify_jwt),
):
    """Execute a simulation and stream results as newline-delimited JSON.

    Each line is a JSON object with a ``type`` field:
      - ``started``  — simulation ID assigned
      - ``progress`` — heartbeat with elapsed seconds
      - ``data``     — chunk of time + output arrays
      - ``completed``— final summary
      - ``error``    — if something went wrong
    """
    _enforce_fmu_claim(claims)
    if _fmu_backend.mode == "station":
        response = await _stream_station_simulation(request, req, claims)
        return response
    _ensure_local_execution_backend("Simulation stream endpoint")

    fmu_filename = claims.get("accessKey") or claims.get("fmuFileName")
    claims_lab_id = _get_claim_lab_id(claims)
    request_lab_id = _normalize_lab_id(req.labId)
    if claims_lab_id and request_lab_id and claims_lab_id != request_lab_id:
        raise HTTPException(status_code=403, detail="JWT not authorised for requested labId")
    lab_id = request_lab_id or claims_lab_id or "unknown"
    _enforce_requested_reservation(claims, req.reservationKey)
    if req.labId is None and claims_lab_id:
        req.labId = claims_lab_id
    if not fmu_filename:
        raise HTTPException(status_code=400, detail="Cannot determine FMU file name from JWT or request")

    fmu_path = _resolve_fmu_path(fmu_filename)

    execution_options = _parse_simulation_options(req.options, claims)
    start_time = execution_options.start_time
    stop_time = execution_options.stop_time
    step_size = execution_options.step_size
    timeout = execution_options.timeout
    fmi_type = _resolve_fmi_type(execution_options.fmi_type, fmu_path)
    solver_name = execution_options.solver_name

    sim_id = uuid4().hex

    async def _event_stream():
        t0 = time.monotonic()
        future: Optional[Future] = None
        job_executor: Any = None
        _acquire_slot(lab_id)
        try:
            # Observation is the durable acceptance gate; only then is the
            # worker released and the `started` event exposed.
            await _record_browser_session_started(request, claims, sim_id)
            job_executor, future = _submit_simulation(
                str(fmu_path), start_time, stop_time, step_size,
                req.parameters, timeout, fmi_type, solver_name,
            )
            if future is None:
                raise RuntimeError("simulation executor returned no future")
            _track_running_future(sim_id, future, lab_id, claims, job_executor)
            yield json.dumps({"type": "started", "simId": sim_id}) + "\n"

            # Heartbeat while simulation runs
            while not future.done():
                elapsed = round(time.monotonic() - t0, 1)
                if elapsed >= timeout:
                    future.cancel()
                    _shutdown_simulation_executor(job_executor, force=True)
                    yield json.dumps({"type": "error", "simId": sim_id, "detail": "Simulation timed out"}) + "\n"
                    return
                yield json.dumps({"type": "progress", "elapsedSeconds": elapsed}) + "\n"
                await asyncio.sleep(1)

            sim_result = future.result()

            # Stream results in chunks (~10 chunks)
            for chunk in _iter_simulation_result_chunks(sim_result):
                yield json.dumps(chunk) + "\n"

            elapsed = round(time.monotonic() - t0, 3)
            yield json.dumps(_build_simulation_completed_event(
                sim_id=sim_id,
                simulation_time=elapsed,
                fmi_type=fmi_type,
                simulation_result=sim_result,
            )) + "\n"

            await _save_history(sim_id, lab_id, claims, fmu_filename, fmi_type,
                                req.parameters, req.options, sim_result, elapsed)

        except Exception as exc:
            logger.exception(
                "Streaming simulation failed for lab %s sim_id=%s",
                str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
                sim_id,
            )
            yield json.dumps(_stream_error_payload(exc, sim_id=sim_id)) + "\n"
        finally:
            _finalize_simulation_tracking(sim_id, lab_id)

    return StreamingResponse(_event_stream(), media_type="application/x-ndjson")
