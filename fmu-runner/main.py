"""
FMU Runner — FastAPI service for FMI Co-Simulation execution.

Endpoints:
  POST /api/v1/simulations/run      — Execute a simulation
  GET  /api/v1/simulations/describe — Describe FMU model metadata
  GET  /health                      — Health check
"""

import os
import time
import json
import logging
import tempfile
import shutil
import asyncio
import math
import io
import zipfile
import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse
from contextlib import asynccontextmanager
try:
    import resource as posix_resource
except ImportError:
    posix_resource = None  # Not available on Windows
from pathlib import Path
from typing import Optional
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, Future
from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4

import aiosqlite
import httpx
from fmpy import read_model_description, simulate_fmu
from fastapi import FastAPI, HTTPException, Depends, Query, WebSocket, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
from xml.etree import ElementTree as ET

from auth import verify_jwt, verify_jwt_token
from fmu_backend import LocalFmuBackend, StationFmuBackend
from realtime_ws import RealtimeWsManager
from station_ws_proxy import StationRealtimeWsProxyManager

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FMU_DATA_PATH = os.getenv("FMU_DATA_PATH", "/app/fmu-data")
MAX_SIMULATION_TIMEOUT = int(os.getenv("MAX_SIMULATION_TIMEOUT", "300"))
MAX_CONCURRENT_PER_MODEL = int(os.getenv("MAX_CONCURRENT_PER_MODEL", "10"))
MAX_STOP_TIME = float(os.getenv("MAX_STOP_TIME", "86400"))  # 24h upper bound
MIN_STEP_SIZE = float(os.getenv("MIN_STEP_SIZE", "1e-6"))    # 1 µs lower bound
HISTORY_DB_PATH = os.getenv("HISTORY_DB_PATH", "/app/data/history.db")
WS_SESSION_QUEUE_SIZE = int(os.getenv("WS_SESSION_QUEUE_SIZE", "64"))
WS_HEARTBEAT_SECONDS = float(os.getenv("WS_HEARTBEAT_SECONDS", "15"))
WS_EXPIRING_NOTICE_SECONDS = int(os.getenv("WS_EXPIRING_NOTICE_SECONDS", "60"))
WS_ATTACH_GRACE_SECONDS = int(os.getenv("WS_ATTACH_GRACE_SECONDS", "120"))
WS_CLEANUP_SECONDS = float(os.getenv("WS_CLEANUP_SECONDS", "15"))
INTERNAL_WS_TOKEN = os.getenv("FMU_INTERNAL_WS_TOKEN", "")
AUTH_SESSION_TICKET_ISSUE_URL = os.getenv(
    "AUTH_SESSION_TICKET_ISSUE_URL",
    "http://blockchain-services:8080/auth/fmu/session-ticket/issue",
)
AUTH_SESSION_TICKET_REDEEM_URL = os.getenv(
    "AUTH_SESSION_TICKET_REDEEM_URL",
    "http://blockchain-services:8080/auth/fmu/session-ticket/redeem",
)
AUTH_SESSION_TICKET_INTERNAL_TOKEN = os.getenv("AUTH_SESSION_TICKET_INTERNAL_TOKEN", "")
FMU_PROXY_RUNTIME_PATH = os.getenv("FMU_PROXY_RUNTIME_PATH", "/app/fmu-proxy-runtime")
FMU_PROXY_GATEWAY_WS_URL = os.getenv("FMU_PROXY_GATEWAY_WS_URL", "")
FMU_PROXY_SIGNING_KEY = os.getenv("FMU_PROXY_SIGNING_KEY", "")
FMU_BACKEND_MODE = os.getenv("FMU_BACKEND_MODE", "local").strip().lower()
FMU_STATION_BASE_URL = os.getenv("FMU_STATION_BASE_URL", "").strip()
FMU_STATION_INTERNAL_TOKEN = os.getenv("FMU_STATION_INTERNAL_TOKEN", "").strip()
FMU_STATION_REQUEST_TIMEOUT = float(os.getenv("FMU_STATION_REQUEST_TIMEOUT", "10"))
PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE = int(os.getenv("PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE", "20"))
WS_CREATE_RATE_LIMIT_PER_MINUTE = int(os.getenv("WS_CREATE_RATE_LIMIT_PER_MINUTE", "30"))

# ---- Structured JSON logging (#23) ----

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

_active_counts: dict[str, int] = defaultdict(int)
_active_lock = Lock()

_proxy_download_hits: dict[str, deque[float]] = defaultdict(deque)
_proxy_download_lock = Lock()


def _normalize_ticket_id(session_ticket: Optional[str]) -> Optional[str]:
    if not session_ticket:
        return None
    token = str(session_ticket).strip()
    if token.startswith("st_"):
        token = token[3:]
    return token[:10] if token else None


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
    """Acquire a concurrency slot for *lab_id*. Raises 429 if limit reached."""
    with _active_lock:
        if _active_counts[lab_id] >= MAX_CONCURRENT_PER_MODEL:
            raise HTTPException(
                status_code=429,
                detail=f"Concurrency limit ({MAX_CONCURRENT_PER_MODEL}) reached for this FMU. Try again shortly.",
            )
        _active_counts[lab_id] += 1


def _release_slot(lab_id: str):
    with _active_lock:
        _active_counts[lab_id] = max(0, _active_counts[lab_id] - 1)


# ---------------------------------------------------------------------------
# Execution pool for simulations
# ---------------------------------------------------------------------------

def _create_executor():
    try:
        return ProcessPoolExecutor(max_workers=4)
    except (PermissionError, OSError) as exc:
        logger.warning("ProcessPoolExecutor unavailable, falling back to ThreadPoolExecutor: %s", exc)
        return ThreadPoolExecutor(max_workers=4)


_executor = _create_executor()

# ---------------------------------------------------------------------------
# Running-simulation registry (for cancellation — #17)
# ---------------------------------------------------------------------------

_running_futures: dict[str, tuple[Future, str]] = {}
_running_lock = Lock()


def _track_running_future(sim_id: str, future: Future, lab_id: str):
    with _running_lock:
        _running_futures[sim_id] = (future, lab_id)


def _finalize_simulation_tracking(sim_id: str, lab_id_fallback: Optional[str] = None):
    """Remove simulation from registry and release one concurrency slot."""
    lab_to_release = lab_id_fallback
    with _running_lock:
        entry = _running_futures.pop(sim_id, None)
    if entry is not None:
        _, lab_to_release = entry
    if lab_to_release is not None:
        _release_slot(lab_to_release)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await _init_db()
    if _realtime_manager is not None:
        await _realtime_manager.start()
    try:
        yield
    finally:
        if _realtime_manager is not None:
            await _realtime_manager.stop()
        await _cleanup_temp_files()


app = FastAPI(title="FMU Runner", version="0.2.0", lifespan=_lifespan)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# #29 — Simulation history (SQLite)
# ---------------------------------------------------------------------------

async def _init_db():
    """Create history DB schema if needed."""
    os.makedirs(os.path.dirname(HISTORY_DB_PATH) or ".", exist_ok=True)
    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS simulation_history (
                id TEXT PRIMARY KEY,
                lab_id TEXT NOT NULL,
                user_sub TEXT,
                fmu_filename TEXT,
                fmi_type TEXT DEFAULT 'CoSimulation',
                parameters TEXT,
                options TEXT,
                result TEXT,
                elapsed_seconds REAL,
                status TEXT DEFAULT 'completed',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_history_lab ON simulation_history(lab_id)")
        await db.commit()


async def _save_history(sim_id, lab_id, user_sub, fmu_filename, fmi_type, params, options, result, elapsed):
    """Persist a completed simulation to SQLite."""
    try:
        async with aiosqlite.connect(HISTORY_DB_PATH) as db:
            await db.execute(
                "INSERT INTO simulation_history (id,lab_id,user_sub,fmu_filename,fmi_type,parameters,options,result,elapsed_seconds) VALUES (?,?,?,?,?,?,?,?,?)",
                (sim_id, str(lab_id), user_sub, fmu_filename, fmi_type, json.dumps(params), json.dumps(options), json.dumps(result), elapsed),
            )
            await db.commit()
    except Exception as exc:
        logger.error("Failed to save simulation history: %s", exc)


# ----- models -----

class SimulationRequest(BaseModel):
    reservationKey: Optional[str] = None
    labId: Optional[str] = None
    parameters: dict = Field(default_factory=dict)
    options: dict = Field(default_factory=dict)


# ----- helpers -----

def _is_within_base(base: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def _normalize_lab_id(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_claim_lab_id(claims: dict) -> Optional[str]:
    return _normalize_lab_id(claims.get("labId"))


def _enforce_fmu_claim(claims: dict):
    resource_type = claims.get("resourceType")
    if resource_type is not None and str(resource_type).lower() != "fmu":
        raise HTTPException(status_code=403, detail="Token is not authorised for FMU endpoints")


def _coerce_epoch_seconds(value) -> Optional[int]:
    """Best-effort conversion of JWT epoch-like values to integer seconds."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        # Handles integer and decimal numeric strings.
        return int(float(text))
    except ValueError:
        return None


def _effective_timeout_seconds(requested_timeout: int, claims: dict) -> int:
    """Clamp timeout by configured max and JWT reservation expiry (exp), if present."""
    capped_timeout = min(requested_timeout, MAX_SIMULATION_TIMEOUT)
    exp_ts = _coerce_epoch_seconds(claims.get("exp"))
    if exp_ts is None:
        return capped_timeout

    remaining = int(math.ceil(exp_ts - time.time()))
    if remaining <= 0:
        raise HTTPException(status_code=401, detail="Reservation token has expired")
    return min(capped_timeout, remaining)


def _resolve_fmu_path(fmu_filename: str) -> Path:
    """Search *FMU_DATA_PATH* for a .fmu file matching *fmu_filename*."""
    # Basic validation: must end with .fmu (#19)
    if not fmu_filename.lower().endswith(".fmu"):
        raise HTTPException(status_code=400, detail="Only .fmu files are accepted")
    base = Path(FMU_DATA_PATH).resolve()
    if not base.is_dir():
        raise HTTPException(status_code=503, detail="FMU data directory is unavailable")
    # Direct match
    direct = (base / fmu_filename).resolve()
    if _is_within_base(base, direct) and direct.is_file():
        return direct
    # Search in provider sub-directories (fmu-data/<provider-wallet>/file.fmu)
    for child in base.iterdir():
        if child.is_dir():
            candidate = (child / fmu_filename).resolve()
            if not _is_within_base(base, candidate):
                continue
            if candidate.is_file():
                return candidate
    raise HTTPException(status_code=404, detail=f"FMU file not found: {fmu_filename}")


def _extract_authorization_header(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth
    return None


def _derive_gateway_ws_url(claims: dict) -> str:
    if FMU_PROXY_GATEWAY_WS_URL:
        return FMU_PROXY_GATEWAY_WS_URL
    aud = str(claims.get("aud") or "").strip()
    if not aud:
        raise HTTPException(status_code=500, detail="Missing aud claim required to derive gateway WS URL")
    parsed = urlparse(aud)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=500, detail="Invalid aud claim required to derive gateway WS URL")
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((ws_scheme, parsed.netloc, "/fmu/api/v1/fmu/sessions", "", "", ""))


def _normalize_xml_value(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _parse_fmi_major_version(value) -> int:
    text = str(value or "").strip()
    if not text:
        return 2
    try:
        return int(text.split(".", 1)[0])
    except ValueError:
        return 2


def _proxy_model_identifier(model_metadata: dict) -> str:
    # Keep a stable identifier so the native runtime binary name stays generic.
    return "decentralabs_proxy"


def _normalize_proxy_fmi3_type(type_name: Optional[str]) -> str:
    normalized = str(type_name or "").strip()
    if normalized in {"Float32", "Float64", "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64", "Boolean", "String"}:
        return normalized
    if normalized == "Enumeration":
        return "Int32"
    if normalized == "Integer":
        return "Int32"
    return "Float64"


def _format_fmi_start_value(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return str(value)


def _collect_variable_dimensions(var) -> list[dict]:
    dimensions = []
    for dimension in getattr(var, "dimensions", []) or []:
        entry = {}
        if getattr(dimension, "start", None) is not None:
            entry["start"] = int(dimension.start)
        if getattr(dimension, "valueReference", None) is not None:
            entry["valueReference"] = int(dimension.valueReference)
        variable = getattr(dimension, "variable", None)
        if variable is not None and getattr(variable, "name", None):
            entry["variableName"] = variable.name
        if entry:
            dimensions.append(entry)
    return dimensions


def _validate_proxy_generation_supported(model_metadata: dict):
    simulation_kind = str(model_metadata.get("simulationKind") or "coSimulation").lower()
    if simulation_kind != "cosimulation":
        raise HTTPException(status_code=422, detail="Generated proxy FMUs currently support only Co-Simulation models")

    if _parse_fmi_major_version(model_metadata.get("fmiVersion")) < 3:
        return

    supported_types = {"Float32", "Float64", "Int32", "UInt64", "Boolean", "String"}
    for variable in model_metadata.get("modelVariables", []):
        if _normalize_proxy_fmi3_type(variable.get("type")) not in supported_types:
            raise HTTPException(
                status_code=422,
                detail=f"Generated FMI 3 proxy FMUs do not yet support variable type: {variable.get('type')}",
            )
        for dimension in variable.get("dimensions", []) or []:
            if "start" not in dimension and "valueReference" not in dimension:
                raise HTTPException(
                    status_code=422,
                    detail=f"Generated FMI 3 proxy FMUs require dimension metadata for variable: {variable.get('name')}",
                )


def _model_metadata_from_model_description(md) -> dict:
    supports_cs = bool(getattr(md, "coSimulation", None))
    supports_me = bool(getattr(md, "modelExchange", None))
    simulation_kind = "coSimulation" if supports_cs else ("modelExchange" if supports_me else "unknown")
    simulation_type = "CoSimulation" if supports_cs else ("ModelExchange" if supports_me else "Unknown")

    default_experiment = getattr(md, "defaultExperiment", None)
    default_start = float(default_experiment.startTime) if default_experiment and default_experiment.startTime is not None else 0.0
    default_stop = float(default_experiment.stopTime) if default_experiment and default_experiment.stopTime is not None else 1.0
    default_step = float(default_experiment.stepSize) if default_experiment and default_experiment.stepSize is not None else 0.01

    variables = []
    for index, var in enumerate(getattr(md, "modelVariables", []), start=1):
        entry = {
            "name": var.name,
            "causality": var.causality or "local",
            "type": str(var.type),
            "variability": getattr(var, "variability", None) or "continuous",
            "valueReference": int(getattr(var, "valueReference", index)),
        }
        if hasattr(var, "initial") and var.initial:
            entry["initial"] = var.initial
        if hasattr(var, "unit") and var.unit:
            entry["unit"] = var.unit
        if hasattr(var, "start") and var.start is not None:
            entry["start"] = var.start
        if hasattr(var, "min") and var.min is not None:
            entry["min"] = var.min
        if hasattr(var, "max") and var.max is not None:
            entry["max"] = var.max
        dimensions = _collect_variable_dimensions(var)
        if dimensions:
            entry["dimensions"] = dimensions
        variables.append(entry)

    metadata = {
        "modelName": _normalize_xml_value(getattr(md, "modelName", None)) or "DecentraLabsProxy",
        "guid": _normalize_xml_value(getattr(md, "guid", None)),
        "instantiationToken": _normalize_xml_value(getattr(md, "instantiationToken", None)),
        "fmiVersion": md.fmiVersion,
        "simulationKind": simulation_kind,
        "simulationType": simulation_type,
        "supportsCoSimulation": supports_cs,
        "supportsModelExchange": supports_me,
        "defaultStartTime": default_start,
        "defaultStopTime": default_stop,
        "defaultStepSize": default_step,
        "modelVariables": variables,
    }
    return metadata


def _public_model_metadata(metadata: dict) -> dict:
    variables = []
    for variable in metadata.get("modelVariables", []):
        entry = {
            "name": variable.get("name"),
            "causality": variable.get("causality", "local"),
            "type": variable.get("type", "Real"),
            "variability": variable.get("variability", "continuous"),
        }
        for optional_key in ("initial", "unit", "start", "min", "max", "dimensions"):
            if optional_key in variable:
                entry[optional_key] = variable[optional_key]
        variables.append(entry)

    payload = {
        "fmiVersion": metadata.get("fmiVersion", "2.0"),
        "simulationKind": metadata.get("simulationKind", "unknown"),
        "simulationType": metadata.get("simulationType", "Unknown"),
        "supportsCoSimulation": bool(metadata.get("supportsCoSimulation")),
        "supportsModelExchange": bool(metadata.get("supportsModelExchange")),
        "defaultStartTime": float(metadata.get("defaultStartTime", 0.0)),
        "defaultStopTime": float(metadata.get("defaultStopTime", 1.0)),
        "defaultStepSize": float(metadata.get("defaultStepSize", 0.01)),
        "modelVariables": variables,
    }
    if metadata.get("instantiationToken"):
        payload["instantiationToken"] = metadata["instantiationToken"]
    return payload


def _local_backend_health_payload() -> dict:
    checks = {"fmuDataPath": False, "executor": False}
    base = Path(FMU_DATA_PATH)
    checks["fmuDataPath"] = base.is_dir()
    fmu_count = sum(1 for _ in base.rglob("*.fmu")) if checks["fmuDataPath"] else 0
    try:
        checks["executor"] = not _executor._broken if hasattr(_executor, "_broken") else True
    except Exception:
        checks["executor"] = False
    overall = all(checks.values())
    return {
        "status": "UP" if overall else "DEGRADED",
        "checks": checks,
        "fmuCount": fmu_count,
        "backendMode": "local",
    }


def _load_local_model_metadata(fmu_filename: str) -> dict:
    fmu_path = _resolve_fmu_path(fmu_filename)
    try:
        md = read_model_description(str(fmu_path))
    except Exception as exc:
        logger.error("Failed to read model description for %s: %s", fmu_filename, exc)
        raise HTTPException(status_code=422, detail=f"Cannot parse FMU: {exc}") from exc
    return _model_metadata_from_model_description(md)


def _list_local_fmus_payload(claimed_file: str) -> dict:
    resolved = _resolve_fmu_path(claimed_file)
    base = Path(FMU_DATA_PATH).resolve()
    if not _is_within_base(base, resolved):
        return {"fmus": []}
    rel = resolved.relative_to(base)
    return {
        "fmus": [{
            "filename": resolved.name,
            "path": str(rel),
            "sizeBytes": resolved.stat().st_size,
            "source": "provisioned",
        }]
    }


def _build_fmu_backend():
    if FMU_BACKEND_MODE == "station":
        logger.info("FMU backend mode selected: station")
        return StationFmuBackend(
            base_url=FMU_STATION_BASE_URL,
            internal_token=FMU_STATION_INTERNAL_TOKEN,
            request_timeout=FMU_STATION_REQUEST_TIMEOUT,
        )

    if FMU_BACKEND_MODE != "local":
        logger.warning("Unknown FMU_BACKEND_MODE=%s, falling back to local", FMU_BACKEND_MODE)

    logger.info("FMU backend mode selected: local")
    return LocalFmuBackend(
        health_loader=_local_backend_health_payload,
        model_metadata_loader=_load_local_model_metadata,
        list_loader=_list_local_fmus_payload,
    )


def _get_station_backend() -> StationFmuBackend:
    if isinstance(_fmu_backend, StationFmuBackend):
        return _fmu_backend
    raise HTTPException(status_code=500, detail="Active FMU backend is not station")


def _simulation_request_payload(req: SimulationRequest) -> dict:
    return {
        "reservationKey": req.reservationKey,
        "labId": req.labId,
        "parameters": req.parameters,
        "options": req.options,
    }


def _ensure_local_execution_backend(feature_name: str):
    if _fmu_backend.supports_local_execution:
        return
    raise HTTPException(
        status_code=501,
        detail=(
            f"{feature_name} is not wired for FMU_BACKEND_MODE={_fmu_backend.mode}. "
            "Use FMU_BACKEND_MODE=local for dev/test until the Station execution backend is implemented."
        ),
    )


async def _stream_station_simulation(request: Request, req: SimulationRequest, claims: dict):
    station_backend = _get_station_backend()
    authorization = _extract_authorization_header(request)
    client, response = await station_backend.open_authorized_simulation_stream(
        claims=claims,
        request_payload=_simulation_request_payload(req),
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


def _build_proxy_model_description_xml(model_metadata: dict) -> bytes:
    _validate_proxy_generation_supported(model_metadata)

    model_name = _normalize_xml_value(model_metadata.get("modelName")) or "DecentraLabsProxy"
    guid = _normalize_xml_value(model_metadata.get("guid")) or "{" + uuid4().hex + "}"
    instantiation_token = _normalize_xml_value(model_metadata.get("instantiationToken")) or guid
    model_identifier = _proxy_model_identifier(model_metadata)
    fmi_major_version = _parse_fmi_major_version(model_metadata.get("fmiVersion"))
    declared_units = {
        _normalize_xml_value(var.get("unit"))
        for var in model_metadata.get("modelVariables", [])
        if str(var.get("type", "Real") or "Real") in {"Real", "Float32", "Float64"}
        and _normalize_xml_value(var.get("unit"))
    }

    root_attributes = {
        "modelName": model_name,
        "generationTool": "DecentraLabs FMU Proxy Generator",
        "generationDateAndTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if fmi_major_version >= 3:
        root_attributes["fmiVersion"] = "3.0"
        root_attributes["instantiationToken"] = instantiation_token
    else:
        root_attributes.update({
            "fmiVersion": "2.0",
            "guid": guid,
            "variableNamingConvention": "flat",
            "numberOfEventIndicators": "0",
        })
    root = ET.Element("fmiModelDescription", root_attributes)

    if fmi_major_version >= 3:
        ET.SubElement(
            root,
            "CoSimulation",
            {
                "modelIdentifier": model_identifier,
                "canHandleVariableCommunicationStepSize": "true",
                "canGetAndSetFMUState": "false",
                "canSerializeFMUState": "false",
            },
        )
    else:
        ET.SubElement(
            root,
            "CoSimulation",
            {
                "modelIdentifier": model_identifier,
                "canHandleVariableCommunicationStepSize": "true",
                "canInterpolateInputs": "false",
                "maxOutputDerivativeOrder": "0",
                "canRunAsynchronuously": "false",
                "canBeInstantiatedOnlyOncePerProcess": "false",
                "canNotUseMemoryManagementFunctions": "true",
                "canGetAndSetFMUstate": "false",
                "canSerializeFMUstate": "false",
                "providesDirectionalDerivative": "false",
            },
        )

    if declared_units:
        unit_definitions = ET.SubElement(root, "UnitDefinitions")
        for unit_name in sorted(declared_units):
            ET.SubElement(unit_definitions, "Unit", {"name": unit_name})

    attrs = {}
    if model_metadata.get("defaultStartTime") is not None:
        attrs["startTime"] = str(model_metadata["defaultStartTime"])
    if model_metadata.get("defaultStopTime") is not None:
        attrs["stopTime"] = str(model_metadata["defaultStopTime"])
    if model_metadata.get("defaultStepSize") is not None:
        attrs["stepSize"] = str(model_metadata["defaultStepSize"])
    if attrs:
        ET.SubElement(root, "DefaultExperiment", attrs)

    model_variables = ET.SubElement(root, "ModelVariables")
    output_indexes = []

    for index, var in enumerate(model_metadata.get("modelVariables", []), start=1):
        var_type = str(var.get("type", "Real") or "Real")
        value_reference = var.get("valueReference")
        if value_reference is None:
            value_reference = index
        scalar_attrs = {
            "name": str(var.get("name") or f"var_{index}"),
            "valueReference": str(value_reference),
        }
        causality = _normalize_xml_value(var.get("causality"))
        variability = _normalize_xml_value(var.get("variability"))
        initial = _normalize_xml_value(var.get("initial"))
        if causality:
            scalar_attrs["causality"] = causality
        if variability:
            scalar_attrs["variability"] = variability
        if initial:
            scalar_attrs["initial"] = initial

        type_attrs = {}
        unit = _normalize_xml_value(var.get("unit"))
        normalized_fmi3_type = _normalize_proxy_fmi3_type(var_type)
        if unit and (var_type == "Real" or normalized_fmi3_type in {"Float32", "Float64"}):
            type_attrs["unit"] = unit
        start_value = _format_fmi_start_value(var.get("start"))
        if start_value is not None and (initial or "").lower() != "calculated":
            type_attrs["start"] = start_value

        if fmi_major_version >= 3:
            type_attrs.update(scalar_attrs)
            typed_variable = ET.SubElement(model_variables, normalized_fmi3_type, type_attrs)
            for dimension in var.get("dimensions", []) or []:
                dimension_attrs = {}
                if dimension.get("start") is not None:
                    dimension_attrs["start"] = str(dimension["start"])
                elif dimension.get("valueReference") is not None:
                    dimension_attrs["valueReference"] = str(dimension["valueReference"])
                if dimension_attrs:
                    ET.SubElement(typed_variable, "Dimension", dimension_attrs)
        else:
            scalar = ET.SubElement(model_variables, "ScalarVariable", scalar_attrs)
            if var_type in ("Integer", "Boolean", "String", "Enumeration"):
                ET.SubElement(scalar, var_type, type_attrs)
            else:
                ET.SubElement(scalar, "Real", type_attrs)

        if (causality or "").lower() == "output":
            output_indexes.append((index, value_reference))

    model_structure = ET.SubElement(root, "ModelStructure")
    if output_indexes:
        if fmi_major_version >= 3:
            for _, value_reference in output_indexes:
                ET.SubElement(model_structure, "Output", {"valueReference": str(value_reference)})
        else:
            outputs = ET.SubElement(model_structure, "Outputs")
            for idx, _ in output_indexes:
                ET.SubElement(outputs, "Unknown", {"index": str(idx)})

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes


def _collect_runtime_files(*, fmi_version: str, model_identifier: str) -> list[tuple[Path, str]]:
    runtime_root = Path(FMU_PROXY_RUNTIME_PATH).resolve()
    binaries_root = (runtime_root / "binaries").resolve()
    if not binaries_root.exists() or not binaries_root.is_dir():
        raise HTTPException(
            status_code=503,
            detail="FMU proxy runtime binaries are not provisioned on Lab Gateway",
        )
    files: list[tuple[Path, str]] = []
    fmi_major_version = _parse_fmi_major_version(fmi_version)
    fmi3_platform_map = {
        "win64": ("x86_64-windows", ".dll"),
        "linux64": ("x86_64-linux", ".so"),
        "darwin64": ("x86_64-darwin", ".dylib"),
    }
    for file_path in binaries_root.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith("."):
            rel_path = file_path.relative_to(binaries_root)
            if fmi_major_version >= 3:
                parts = rel_path.parts
                if not parts:
                    continue
                platform = fmi3_platform_map.get(parts[0])
                if platform is None:
                    continue
                platform_dir, expected_suffix = platform
                archive_name = f"binaries/{platform_dir}/{model_identifier}{expected_suffix}"
            else:
                archive_name = file_path.relative_to(runtime_root).as_posix()
            rel = archive_name
            files.append((file_path, rel))
    if not files:
        raise HTTPException(
            status_code=503,
            detail="FMU proxy runtime binaries are not provisioned on Lab Gateway",
        )
    return files


async def _issue_session_ticket(
    authorization: str,
    *,
    lab_id: str,
    reservation_key: Optional[str],
    request_id: Optional[str] = None,
) -> tuple[str, int]:
    headers = {"Content-Type": "application/json", "Authorization": authorization}
    if AUTH_SESSION_TICKET_INTERNAL_TOKEN:
        headers["X-Access-Token"] = AUTH_SESSION_TICKET_INTERNAL_TOKEN

    payload = {"labId": str(lab_id)}
    if reservation_key:
        payload["reservationKey"] = reservation_key

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(AUTH_SESSION_TICKET_ISSUE_URL, headers=headers, json=payload)

    if response.status_code >= 400:
        detail_text = response.text
        try:
            detail_json = response.json()
            detail_text = detail_json.get("error") or detail_json.get("message") or detail_text
        except Exception:
            pass
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Unable to issue session ticket: {detail_text}",
        )

    data = response.json()
    session_ticket = str(data.get("sessionTicket") or "").strip()
    expires_at = _coerce_epoch_seconds(data.get("expiresAt"))
    if not session_ticket or expires_at is None:
        raise HTTPException(status_code=500, detail="Invalid session ticket response from auth service")
    logger.info(
        "Issued FMU session ticket request_id=%s lab_id=%s reservation_key=%s ticket_id=%s expires_at=%s",
        request_id or "-",
        lab_id,
        reservation_key or "-",
        _normalize_ticket_id(session_ticket) or "-",
        expires_at,
    )
    return session_ticket, expires_at


async def _redeem_session_ticket(
    *,
    session_ticket: str,
    lab_id: Optional[str],
    reservation_key: Optional[str],
    request_id: Optional[str] = None,
) -> dict:
    headers = {"Content-Type": "application/json"}
    if AUTH_SESSION_TICKET_INTERNAL_TOKEN:
        headers["X-Access-Token"] = AUTH_SESSION_TICKET_INTERNAL_TOKEN
    payload = {"sessionTicket": session_ticket}
    if lab_id:
        payload["labId"] = str(lab_id)
    if reservation_key:
        payload["reservationKey"] = str(reservation_key)

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(AUTH_SESSION_TICKET_REDEEM_URL, headers=headers, json=payload)

    if response.status_code >= 400:
        detail = {"error": response.text}
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = payload
        except Exception:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)

    payload = response.json()
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, dict):
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "error": "Invalid ticket redeem response"})
    logger.info(
        "Redeemed FMU session ticket request_id=%s lab_id=%s reservation_key=%s ticket_id=%s",
        request_id or "-",
        lab_id or "-",
        reservation_key or "-",
        _normalize_ticket_id(session_ticket) or "-",
    )
    return claims


_fmu_backend = _build_fmu_backend()


class _UnsupportedRealtimeManager:
    async def start(self):
        return

    async def stop(self):
        return

    async def handle_websocket(self, websocket: WebSocket, *, internal: bool):
        await websocket.accept()
        message = (
            f"Realtime FMU sessions are not wired for FMU_BACKEND_MODE={_fmu_backend.mode}. "
            "Use FMU_BACKEND_MODE=local for dev/test until the Station execution backend is implemented."
        )
        await websocket.send_json({
            "type": "error",
            "code": "NOT_IMPLEMENTED",
            "message": message,
            "retryable": False,
        })
        await websocket.close(code=1013)


if _fmu_backend.supports_local_execution:
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
        ws_cleanup_seconds=WS_CLEANUP_SECONDS,
        internal_ws_token=INTERNAL_WS_TOKEN,
        ws_create_rate_limit_per_minute=WS_CREATE_RATE_LIMIT_PER_MINUTE,
    )
else:
    _realtime_manager = _UnsupportedRealtimeManager()


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
            posix_resource.setrlimit(posix_resource.RLIMIT_CPU, (timeout, timeout + 5))
            # 1 GB virtual memory limit
            posix_resource.setrlimit(posix_resource.RLIMIT_AS, (1 * 1024 ** 3, 1 * 1024 ** 3))
    except Exception:
        pass  # May fail on non-Linux or if not root

    sim_kwargs = dict(
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
    col_names = list(result.dtype.names)
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

@app.get("/health")
async def health():
    """Backend-aware health check for the active FMU backend mode."""
    return await _fmu_backend.health()


@app.websocket("/api/v1/fmu/sessions")
async def fmu_realtime_sessions(websocket: WebSocket):
    await _realtime_manager.handle_websocket(websocket, internal=False)


@app.websocket("/internal/fmu/sessions")
async def fmu_realtime_sessions_internal(websocket: WebSocket):
    await _realtime_manager.handle_websocket(websocket, internal=True)


@app.get("/api/v1/fmu/proxy/{lab_id}")
async def download_proxy_fmu(
    lab_id: str,
    request: Request,
    reservationKey: Optional[str] = Query(None),
    claims: dict = Depends(verify_jwt),
):
    """Generate and download a reservation-scoped FMU proxy artifact."""
    _enforce_fmu_claim(claims)

    claim_lab_id = _get_claim_lab_id(claims)
    if claim_lab_id and str(claim_lab_id) != str(lab_id):
        raise HTTPException(status_code=403, detail="Token is not authorised for requested labId")

    claim_reservation_key = str(claims.get("reservationKey") or "").strip()
    if reservationKey and claim_reservation_key and reservationKey.lower() != claim_reservation_key.lower():
        raise HTTPException(status_code=403, detail="Token is not authorised for requested reservationKey")
    effective_reservation_key = reservationKey or claim_reservation_key
    if not effective_reservation_key:
        raise HTTPException(status_code=400, detail="Missing reservationKey")

    claim_sub = str(claims.get("sub") or "anonymous")
    rate_key = f"{claim_sub}:{lab_id}"
    if not _allow_proxy_download(rate_key):
        raise HTTPException(status_code=429, detail="Proxy download rate limit exceeded. Retry shortly.")

    authorization = _extract_authorization_header(request)
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing bearer token required to issue session ticket")

    fmu_filename = claims.get("accessKey") or claims.get("fmuFileName")
    if not fmu_filename:
        raise HTTPException(status_code=400, detail="Cannot determine FMU file name from token")

    session_ticket, ticket_expiry = await _issue_session_ticket(
        authorization,
        lab_id=str(lab_id),
        reservation_key=effective_reservation_key,
        request_id=f"proxy_{uuid4().hex[:8]}",
    )
    gateway_ws_url = _derive_gateway_ws_url(claims)
    model_metadata = await _fmu_backend.get_authorized_model_metadata(
        claims=claims,
        requested_fmu_filename=str(fmu_filename),
    )
    model_xml = _build_proxy_model_description_xml(model_metadata)
    proxy_fmi_version = "3.0" if _parse_fmi_major_version(model_metadata.get("fmiVersion")) >= 3 else "2.0.3"
    proxy_model_identifier = _proxy_model_identifier(model_metadata)
    runtime_files = _collect_runtime_files(
        fmi_version=proxy_fmi_version,
        model_identifier=proxy_model_identifier,
    )

    config_payload = {
        "protocolVersion": "1.0",
        "fmiVersion": proxy_fmi_version,
        "gatewayWsUrl": gateway_ws_url,
        "labId": str(lab_id),
        "reservationKey": effective_reservation_key,
        "sessionTicket": session_ticket,
        "ticketExpiresAt": ticket_expiry,
        "timeMode": "simtime",
    }

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("modelDescription.xml", model_xml)
        archive.writestr("resources/config.json", json.dumps(config_payload, separators=(",", ":")))
        for file_path, archive_name in runtime_files:
            archive.write(file_path, archive_name)

    archive_bytes = archive_buffer.getvalue()
    artifact_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    proxy_name = f"fmu-proxy-lab-{lab_id}.fmu"
    headers = {
        "Content-Disposition": f'attachment; filename="{proxy_name}"',
        "X-Proxy-Artifact-Sha256": artifact_sha256,
    }
    if FMU_PROXY_SIGNING_KEY:
        signature = hmac.new(
            FMU_PROXY_SIGNING_KEY.encode("utf-8"),
            archive_bytes,
            hashlib.sha256,
        ).hexdigest()
        headers["X-Proxy-Artifact-Signature"] = f"hmac-sha256={signature}"

    logger.info(
        "Generated proxy FMU lab_id=%s reservation_key=%s ticket_id=%s bytes=%s sha256=%s signed=%s",
        lab_id,
        effective_reservation_key,
        _normalize_ticket_id(session_ticket) or "-",
        len(archive_bytes),
        artifact_sha256,
        "yes" if FMU_PROXY_SIGNING_KEY else "no",
    )
    return Response(content=archive_bytes, media_type="application/octet-stream", headers=headers)


@app.get("/api/v1/simulations/describe")
async def describe(
    fmuFileName: str = Query(..., description="Name of the .fmu file"),
    claims: dict = Depends(verify_jwt),
):
    """Return model metadata parsed from the FMU's modelDescription.xml."""
    _enforce_fmu_claim(claims)
    metadata = await _fmu_backend.get_authorized_model_metadata(
        claims=claims,
        requested_fmu_filename=fmuFileName,
    )
    return _public_model_metadata(metadata)


@app.post("/api/v1/simulations/run")
async def run_simulation(
    req: SimulationRequest,
    request: Request,
    claims: dict = Depends(verify_jwt),
):
    """Execute an FMU simulation and return results.

    Supports CoSimulation and ModelExchange (#31). Auto-detects FMI type from
    model description when ``options.fmiType`` is absent.
    """
    _enforce_fmu_claim(claims)
    if _fmu_backend.mode == "station":
        return await _get_station_backend().run_authorized_simulation(
            claims=claims,
            request_payload=_simulation_request_payload(req),
            authorization=_extract_authorization_header(request),
        )
    _ensure_local_execution_backend("Simulation run endpoint")

    # Determine FMU filename from JWT claims or request
    fmu_filename = claims.get("accessKey") or claims.get("fmuFileName")
    claims_lab_id = _get_claim_lab_id(claims)
    request_lab_id = _normalize_lab_id(req.labId)
    if claims_lab_id and request_lab_id and claims_lab_id != request_lab_id:
        raise HTTPException(status_code=403, detail="JWT not authorised for requested labId")
    lab_id = request_lab_id or claims_lab_id or "unknown"

    if req.labId is None and claims_lab_id:
        req.labId = claims_lab_id

    if not fmu_filename:
        raise HTTPException(status_code=400, detail="Cannot determine FMU file name from JWT or request")

    fmu_path = _resolve_fmu_path(fmu_filename)

    # Options
    start_time = float(req.options.get("startTime", 0))
    stop_time = float(req.options.get("stopTime", 10))
    step_size = float(req.options.get("stepSize", 0.01))
    requested_timeout = int(req.options.get("timeout", MAX_SIMULATION_TIMEOUT))

    if stop_time <= start_time:
        raise HTTPException(status_code=400, detail="stopTime must be greater than startTime")
    if step_size <= 0:
        raise HTTPException(status_code=400, detail="stepSize must be positive")
    if requested_timeout <= 0:
        raise HTTPException(status_code=400, detail="timeout must be positive")
    timeout = _effective_timeout_seconds(requested_timeout, claims)
    # Upper/lower safety bounds (#24)
    if stop_time > MAX_STOP_TIME:
        raise HTTPException(status_code=400, detail=f"stopTime exceeds maximum ({MAX_STOP_TIME}s)")
    if step_size < MIN_STEP_SIZE:
        raise HTTPException(status_code=400, detail=f"stepSize below minimum ({MIN_STEP_SIZE}s)")

    # --- FMI type auto-detection (#31) ---
    fmi_type = req.options.get("fmiType", None)
    solver_name = req.options.get("solver", "Euler")
    if not fmi_type:
        try:
            md = read_model_description(str(fmu_path))
            fmi_type = "CoSimulation" if md.coSimulation else ("ModelExchange" if md.modelExchange else "CoSimulation")
        except Exception:
            fmi_type = "CoSimulation"

    # Concurrency check
    _acquire_slot(lab_id)

    sim_id = uuid4().hex
    t0 = time.monotonic()
    future: Optional[Future] = None
    cleanup_deferred = False
    try:
        future = _executor.submit(
            _run_simulation,
            str(fmu_path),
            start_time,
            stop_time,
            step_size,
            req.parameters,
            timeout,
            fmi_type,
            solver_name,
        )
        _track_running_future(sim_id, future, lab_id)
        try:
            sim_result = await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout)
        except asyncio.TimeoutError as exc:
            if not future.done():
                future.cancel()
                cleanup_deferred = True
                future.add_done_callback(lambda _f, sid=sim_id: _finalize_simulation_tracking(sid))
            raise HTTPException(status_code=504, detail="Simulation timed out") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Simulation failed for lab %s: %s", lab_id, exc)
        raise HTTPException(status_code=500, detail=f"Simulation error: {exc}") from exc
    finally:
        if not cleanup_deferred:
            _finalize_simulation_tracking(sim_id, lab_id)

    elapsed = round(time.monotonic() - t0, 3)
    logger.info("Simulation completed for lab %s in %.3fs", lab_id, elapsed)

    # Persist to history DB (#29)
    await _save_history(sim_id, lab_id, claims.get("sub"), fmu_filename, fmi_type,
                        req.parameters, req.options, sim_result, elapsed)

    return {
        "status": "completed",
        "simId": sim_id,
        "simulationTime": elapsed,
        "fmiType": fmi_type,
        **sim_result,
    }


# ---------------------------------------------------------------------------
# #16 — List available FMU files
# ---------------------------------------------------------------------------

@app.get("/api/v1/fmu/list")
async def list_fmus(claims: dict = Depends(verify_jwt)):
    """Return only the FMU file authorised by the caller token."""
    _enforce_fmu_claim(claims)
    return await _fmu_backend.list_authorized_fmu(claims=claims)


# ---------------------------------------------------------------------------
# #17 — Cancel a running simulation
# ---------------------------------------------------------------------------

@app.post("/api/v1/simulations/{sim_id}/cancel")
async def cancel_simulation(sim_id: str, _claims: dict = Depends(verify_jwt)):
    """Attempt to cancel a running simulation by its ID."""
    _ensure_local_execution_backend("Simulation cancel endpoint")
    with _running_lock:
        entry = _running_futures.get(sim_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Simulation not found or already finished")
    future, _lab_id = entry
    cancelled = future.cancel()
    if not cancelled and future.running():
        return {"status": "running", "detail": "Cannot cancel - simulation already executing in worker process"}
    _finalize_simulation_tracking(sim_id)
    return {"status": "cancelled"}

# ---------------------------------------------------------------------------
# #20 — Temp file cleanup (FMPy extracts FMUs to tempdir)
# ---------------------------------------------------------------------------

async def _cleanup_temp_files():
    """Best-effort cleanup of FMPy temp dirs on shutdown."""
    tmp = Path(tempfile.gettempdir())
    removed = 0
    for entry in tmp.iterdir():
        # FMPy creates dirs matching the pattern tmp* containing modelDescription.xml
        if entry.is_dir() and entry.name.startswith("tmp") and (entry / "modelDescription.xml").exists():
            try:
                shutil.rmtree(entry)
                removed += 1
            except Exception:
                pass
    if removed:
        logger.info("Cleaned up %d FMPy temp directories", removed)


# ---------------------------------------------------------------------------
# #18 — NDJSON Streaming endpoint
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
        return await _stream_station_simulation(request, req, claims)
    _ensure_local_execution_backend("Simulation stream endpoint")

    fmu_filename = claims.get("accessKey") or claims.get("fmuFileName")
    claims_lab_id = _get_claim_lab_id(claims)
    request_lab_id = _normalize_lab_id(req.labId)
    if claims_lab_id and request_lab_id and claims_lab_id != request_lab_id:
        raise HTTPException(status_code=403, detail="JWT not authorised for requested labId")
    lab_id = request_lab_id or claims_lab_id or "unknown"
    if req.labId is None and claims_lab_id:
        req.labId = claims_lab_id
    if not fmu_filename:
        raise HTTPException(status_code=400, detail="Cannot determine FMU file name from JWT or request")

    fmu_path = _resolve_fmu_path(fmu_filename)

    start_time = float(req.options.get("startTime", 0))
    stop_time = float(req.options.get("stopTime", 10))
    step_size = float(req.options.get("stepSize", 0.01))
    requested_timeout = int(req.options.get("timeout", MAX_SIMULATION_TIMEOUT))

    if stop_time <= start_time:
        raise HTTPException(status_code=400, detail="stopTime must be greater than startTime")
    if step_size <= 0:
        raise HTTPException(status_code=400, detail="stepSize must be positive")
    if requested_timeout <= 0:
        raise HTTPException(status_code=400, detail="timeout must be positive")
    timeout = _effective_timeout_seconds(requested_timeout, claims)
    if stop_time > MAX_STOP_TIME:
        raise HTTPException(status_code=400, detail=f"stopTime exceeds maximum ({MAX_STOP_TIME}s)")
    if step_size < MIN_STEP_SIZE:
        raise HTTPException(status_code=400, detail=f"stepSize below minimum ({MIN_STEP_SIZE}s)")

    fmi_type = req.options.get("fmiType", None)
    solver_name = req.options.get("solver", "Euler")
    if not fmi_type:
        try:
            md = read_model_description(str(fmu_path))
            fmi_type = "CoSimulation" if md.coSimulation else ("ModelExchange" if md.modelExchange else "CoSimulation")
        except Exception:
            fmi_type = "CoSimulation"

    _acquire_slot(lab_id)
    sim_id = uuid4().hex

    async def _event_stream():
        t0 = time.monotonic()
        cleanup_deferred = False
        yield json.dumps({"type": "started", "simId": sim_id}) + "\n"

        future = _executor.submit(
            _run_simulation, str(fmu_path), start_time, stop_time, step_size,
            req.parameters, timeout, fmi_type, solver_name,
        )
        _track_running_future(sim_id, future, lab_id)

        try:
            # Heartbeat while simulation runs
            while not future.done():
                elapsed = round(time.monotonic() - t0, 1)
                if elapsed >= timeout:
                    future.cancel()
                    cleanup_deferred = True
                    future.add_done_callback(lambda _f, sid=sim_id: _finalize_simulation_tracking(sid))
                    yield json.dumps({"type": "error", "simId": sim_id, "detail": "Simulation timed out"}) + "\n"
                    return
                yield json.dumps({"type": "progress", "elapsedSeconds": elapsed}) + "\n"
                await asyncio.sleep(1)

            sim_result = future.result()

            # Stream results in chunks (~10 chunks)
            time_data = sim_result.get("time", [])
            chunk_size = max(1, len(time_data) // 10)
            total_chunks = max(1, -(-len(time_data) // chunk_size))  # ceil division
            for idx in range(0, len(time_data), chunk_size):
                chunk = {
                    "type": "data",
                    "chunkIndex": idx // chunk_size,
                    "totalChunks": total_chunks,
                    "time": time_data[idx:idx + chunk_size],
                    "outputs": {k: v[idx:idx + chunk_size] for k, v in sim_result.get("outputs", {}).items()},
                }
                yield json.dumps(chunk) + "\n"

            elapsed = round(time.monotonic() - t0, 3)
            yield json.dumps({
                "type": "completed",
                "simId": sim_id,
                "simulationTime": elapsed,
                "fmiType": fmi_type,
                "outputVariables": sim_result.get("outputVariables", []),
            }) + "\n"

            await _save_history(sim_id, lab_id, claims.get("sub"), fmu_filename, fmi_type,
                                req.parameters, req.options, sim_result, elapsed)

        except Exception as exc:
            logger.error("Streaming simulation failed for lab %s: %s", lab_id, exc)
            yield json.dumps({"type": "error", "detail": str(exc)}) + "\n"
        finally:
            if not cleanup_deferred:
                _finalize_simulation_tracking(sim_id, lab_id)

    return StreamingResponse(_event_stream(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# #29 — Simulation history endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/simulations/history")
async def get_history(
    labId: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    claims: dict = Depends(verify_jwt),
):
    """Return paginated simulation history for the lab authorised in the token."""
    _enforce_fmu_claim(claims)
    _ensure_local_execution_backend("Simulation history endpoint")
    claim_lab_id = _get_claim_lab_id(claims)
    if not claim_lab_id:
        raise HTTPException(status_code=403, detail="Token has no authorised labId")
    requested_lab_id = _normalize_lab_id(labId)
    if requested_lab_id and requested_lab_id != claim_lab_id:
        raise HTTPException(status_code=403, detail="Token is not authorised for requested labId")
    effective_lab_id = requested_lab_id or claim_lab_id

    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, lab_id, user_sub, fmu_filename, fmi_type, elapsed_seconds, status, created_at "
            "FROM simulation_history WHERE lab_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (effective_lab_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return {"simulations": [dict(row) for row in rows]}


@app.get("/api/v1/simulations/{sim_id}/result")
async def get_simulation_result(sim_id: str, claims: dict = Depends(verify_jwt)):
    """Retrieve full simulation result by ID."""
    _enforce_fmu_claim(claims)
    _ensure_local_execution_backend("Simulation result endpoint")
    claim_lab_id = _get_claim_lab_id(claims)
    if not claim_lab_id:
        raise HTTPException(status_code=403, detail="Token has no authorised labId")

    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM simulation_history WHERE id = ?", (sim_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Simulation not found")
    result = dict(row)
    if _normalize_lab_id(result.get("lab_id")) != claim_lab_id:
        raise HTTPException(status_code=403, detail="Token is not authorised for requested simulation result")
    for key in ("parameters", "options", "result"):
        if result.get(key):
            result[key] = json.loads(result[key])
    return result



