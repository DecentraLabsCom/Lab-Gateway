#!/usr/bin/env python3
"""
Ops worker: WoL + WinRM wrapper + heartbeat poller for Lab Station hosts.
Exposes a small Flask API and optional scheduler.
"""
import errno
import json
import hmac
import hashlib
import base64
import ipaddress
import logging
import os
import re
import socket
import time
from datetime import datetime, timezone, timedelta
from threading import RLock
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import quote
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, Response, jsonify, request, stream_with_context
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException as WerkzeugHTTPException
from werkzeug.utils import secure_filename
from wakeonlan import send_magic_packet
import requests
import winrm
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from apscheduler.schedulers.background import BackgroundScheduler
from waitress import serve
import aas_generator
from errors import (
    WINRM_CERTIFICATE_EXPIRED_MESSAGE,
    WINRM_CERTIFICATE_INVALID_MESSAGE,
    WINRM_CERTIFICATE_NOT_YET_VALID_MESSAGE,
    WINRM_CERTIFICATE_REQUIRED_MESSAGE,
    WINRM_CREDENTIALS_REQUIRED_MESSAGE,
    WINRM_FINGERPRINT_CONFIRMATION_REQUIRED_MESSAGE,
    WINRM_FINGERPRINT_MISMATCH_MESSAGE,
    WINRM_TLS_FAILED_MESSAGE,
    WINRM_TRUST_ERROR_MESSAGES,
    WINRM_TRUST_REF_MISMATCH_MESSAGE,
    WINRM_TRUST_REQUIRED_CODE,
    WINRM_TRUST_REQUIRED_MESSAGE,
    WinRMTrustError,
    is_missing_winrm_credentials_error,
)
from winrm_trust import (
    _certificate_datetime,
    _certificate_matches_host,
    _dns_name_matches,
    _format_certificate_datetime,
    _is_valid_ip_address,
    _parse_winrm_certificate_bytes as _parse_winrm_certificate_bytes_impl,
    _resolve_winrm_trust_file_path,
    _winrm_certificate_metadata,
    validate_winrm_certificate as _validate_winrm_certificate_impl,
    WINRM_CERTIFICATE_MAX_BYTES as _WINRM_CERTIFICATE_MAX_BYTES_DEFAULT,
)
from winrm_trust_store import (
    delete_trust_files as _delete_trust_files_impl,
    materialize_trust_pem as _materialize_trust_pem_impl,
    read_trust_metadata as _read_trust_metadata_file,
    write_trust_bytes as _write_trust_bytes_impl,
    write_trust_metadata as _write_trust_metadata_file,
)
from winrm_trust_service import inspect_winrm_trust as _inspect_winrm_trust_impl
from winrm_trust_service import (
    load_winrm_trust as _load_winrm_trust_impl,
    refresh_winrm_trust_store as _refresh_winrm_trust_store_impl,
)
from winrm_session_policy import (
    build_winrm_endpoint as _build_winrm_endpoint_impl,
    resolve_winrm_connection_policy as _resolve_winrm_connection_policy_impl,
)
from winrm_session_factory import (
    create_winrm_session as _create_winrm_session_impl,
)
from winrm_command_execution import (
    run_winrm_method as _run_winrm_method_impl,
)
from winrm_command_service import (
    read_remote_file as _read_remote_file_impl,
    remove_remote_file as _remove_remote_file_impl,
    run_remote_powershell as _run_remote_powershell_impl,
    run_labstation_command as _run_labstation_command_impl,
    write_remote_file as _write_remote_file_impl,
)
from winrm_command_builders import (
    build_labstation_command as _build_labstation_command_impl,
    build_read_remote_file_command as _build_read_remote_file_command_impl,
    build_remove_remote_file_command as _build_remove_remote_file_command_impl,
    build_write_remote_file_command as _build_write_remote_file_command_impl,
)
from heartbeat_values import (
    choose_wol_mac as _choose_wol_mac_impl,
    extract_nic_candidates_from_heartbeat as _extract_nic_candidates_from_heartbeat_impl,
    normalize_mac as _normalize_mac_impl,
    parse_boolish as _parse_boolish_impl,
)
from heartbeat_values import suggest_mac_from_heartbeat as _suggest_mac_from_heartbeat_impl
from heartbeat_service import poll_heartbeat as _poll_heartbeat_impl
from heartbeat_stream import generate_heartbeat_stream as _generate_heartbeat_stream_impl
from heartbeat_poller import poll_all_hosts as _poll_all_hosts_impl
from heartbeat_route import handle_heartbeat_poll as _handle_heartbeat_poll_impl
from heartbeat_stream_route import handle_heartbeat_stream as _handle_heartbeat_stream_route_impl
from winrm_credentials_resolution import (
    resolve_winrm_credentials as _resolve_winrm_credentials_impl,
)
from host_catalog import validate_winrm_catalog as _validate_winrm_catalog_impl
from host_registry import HostRegistry
from host_config_service import (
    load_dynamic_config as _load_dynamic_config_impl,
    load_host_config as _load_host_config_impl,
    update_dynamic_host as _update_dynamic_host_impl,
    upsert_dynamic_host as _upsert_dynamic_host_impl,
    write_dynamic_config as _write_dynamic_config_impl,
)
from host_reload_service import reload_hosts as _reload_hosts_impl
from host_inventory_values import (
    safe_host_inventory_entry as _safe_host_inventory_entry_impl,
)
from host_inventory_service import (
    build_host_inventory as _build_host_inventory_impl,
)
from host_discovery_values import (
    probe_labstation_http as _probe_labstation_http_impl,
    response_looks_like_labstation as _response_looks_like_labstation_impl,
)
from host_discovery_service import (
    discover_labstation_candidate as _discover_labstation_candidate_impl,
)
from host_heartbeat_discovery import (
    discover_heartbeat_hint as _discover_heartbeat_hint_impl,
)
from host_heartbeat_paths import (
    build_heartbeat_path_candidates as _build_heartbeat_path_candidates_impl,
    query_labstation_task_heartbeat_path as _query_labstation_task_heartbeat_path_impl,
)
from guacamole_connection_lookup import (
    guacamole_name_candidates as _guacamole_name_candidates_impl,
    resolve_guacamole_connection as _resolve_guacamole_connection_impl,
)
from guacamole_connection_values import (
    parse_guacamole_selector as _parse_guacamole_selector_impl,
    safe_connection_response as _safe_connection_response_impl,
)
from guacamole_connection_route import (
    handle_guacamole_connections as _handle_guacamole_connections_impl,
)
from guacamole_cleanup_route import handle_guacamole_cleanup as _handle_guacamole_cleanup_impl
from guacamole_provision_route import handle_guacamole_provision as _handle_guacamole_provision_impl
from guacamole_catalog_service import (
    load_guacamole_connections as _load_guacamole_connections_impl,
)
from guacamole_dsn import build_guacamole_dsn as _build_guacamole_dsn_impl
from ops_dsn import build_ops_dsn as _build_ops_dsn_impl
from datetime_values import to_utc as _to_utc_impl
from input_values import (
    normalize_args as _normalize_args_impl,
    parse_bool as _parse_bool_impl,
    parse_recipients as _parse_recipients_impl,
)
from database_health import database_is_usable as _database_is_usable_impl
from demo_values import (
    canonical_demo_lab_id as _canonical_demo_lab_id_impl,
    get_mandatory_field as _get_mandatory_field_impl,
)
from health_values import build_health_response as _build_health_response_impl
from operation_values import rows_to_operations as _rows_to_operations_impl
from operations_route import handle_operations_recent as _handle_operations_recent_impl
from hosts_route import handle_hosts_inventory as _handle_hosts_inventory_impl
from hosts_reload_route import handle_hosts_reload as _handle_hosts_reload_impl
from hosts_discover_route import handle_hosts_discover as _handle_hosts_discover_impl
from timeline_route import handle_reservation_timeline as _handle_reservation_timeline_impl
from aas_sync_route import handle_aas_sync as _handle_aas_sync_impl
from winrm_trust_route import handle_winrm_trust_get as _handle_winrm_trust_get_impl
from host_provisioning_values import (
    build_provisioned_host as _build_provisioned_host_impl,
    normalize_labs as _normalize_labs_impl,
    sanitize_host_name as _sanitize_host_name_impl,
    validate_labs_against_candidates as _validate_labs_against_candidates_impl,
)
from power.api import power_bp
from power.models import ValidationError as PowerValidationError
from power.credentials import PowerCredentialStore
from power.persistence import PowerOperationStore
from power.service import PowerRuntime

APP = Flask(__name__)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


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


def _sanitize_log_value(value: Any) -> str:
    """Keep request-derived values on one physical log line."""
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def _as_utc_datetime(value: Any) -> Optional[datetime]:
    """Normalize a reservation timestamp to an aware UTC datetime."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_reservation_datetime(value: Any) -> Optional[datetime]:
    return _as_utc_datetime(value)


def _is_valid_ping_target(target: str) -> bool:
    """Validate a DNS name without a backtracking-prone regular expression."""
    if not target or len(target) > 253:
        return False
    labels = target.rstrip(".").split(".")
    if not labels or any(not label or len(label) > 63 for label in labels):
        return False
    return all(
        label[0].isalnum()
        and label[-1].isalnum()
        and all(char.isalnum() or char == "-" for char in label)
        for label in labels
    )


def _request_id() -> str:
    """Return a bounded correlation id without echoing arbitrary header data."""
    candidate = str(request.headers.get("X-Request-ID") or "").strip()
    return candidate if _REQUEST_ID_RE.fullmatch(candidate) else uuid4().hex


def internal_error_response(
    context: str,
    exc: BaseException,
    *,
    success: Optional[bool] = None,
    status: int = 500,
):
    """Log the detailed exception and expose only a stable public error contract."""
    request_id = _request_id()
    logging.exception(
        "Ops Worker request failed context=%s",
        _sanitize_log_value(context),
    )
    payload: Dict[str, Any] = {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": request_id,
    }
    if success is not None:
        payload["success"] = success
    return jsonify(payload), status


@APP.errorhandler(Exception)
def handle_unexpected_exception(exc: Exception):
    if isinstance(exc, WerkzeugHTTPException):
        return exc
    return internal_error_response("Unhandled Ops Worker request", exc)

CONFIG_PATH = os.getenv("OPS_CONFIG", os.path.join(os.path.dirname(__file__), "hosts.json"))
DYNAMIC_CONFIG_PATH = os.getenv("OPS_DYNAMIC_CONFIG", "/app/data/hosts.json")
OPS_CREDENTIALS_PATH = os.getenv("OPS_CREDENTIALS_PATH", "/app/data/winrm-credentials.json")
OPS_WINRM_TRUST_PATH = os.getenv("OPS_WINRM_TRUST_PATH", "/app/data/winrm-certificates")
POWER_CONFIG_PATH = os.getenv("OPS_POWER_CONFIG", "/app/data/power-controllers.json")
POWER_STATUS_CACHE_SECONDS = max(
    0.0,
    float(os.getenv("OPS_POWER_STATUS_CACHE_SECONDS", "5")),
)
MYSQL_DSN = os.getenv("MYSQL_DSN")
GUACAMOLE_MYSQL_DSN = os.getenv("GUACAMOLE_MYSQL_DSN")
OPS_MYSQL_DATABASE = os.getenv("OPS_MYSQL_DATABASE") or os.getenv("BLOCKCHAIN_MYSQL_DATABASE")
GUACAMOLE_MYSQL_DATABASE = os.getenv("GUACAMOLE_MYSQL_DATABASE") or os.getenv("MYSQL_DATABASE")
MYSQL_HOSTNAME = os.getenv("MYSQL_HOSTNAME") or os.getenv("MYSQL_HOST") or "mysql"
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
# Database principals are deliberately separate: the worker needs DML on the
# backend schema and a narrower DML principal on Guacamole's schema.
OPS_MYSQL_USER = os.getenv("OPS_BACKEND_MYSQL_USER", "")
OPS_MYSQL_PASSWORD = _env_or_secret_file("OPS_BACKEND_MYSQL_PASSWORD")
GUACAMOLE_MYSQL_USER = os.getenv("OPS_GUACAMOLE_MYSQL_USER", "")
GUACAMOLE_MYSQL_PASSWORD = _env_or_secret_file("OPS_GUACAMOLE_MYSQL_PASSWORD")
DEMO_USER = (os.getenv("DEMO_USER") or "demo-lab-disabled").strip()
DEMO_LAB_ID = (os.getenv("DEMO_LAB_ID") or "").strip()
DEMO_CONNECTION_ID = (os.getenv("DEMO_CONNECTION_ID") or "").strip()
DEMO_HEARTBEAT_MAX_AGE_SECONDS = max(30, int(os.getenv("DEMO_HEARTBEAT_MAX_AGE_SECONDS", "180")))
DEMO_OPERATION_ID_RE = re.compile(r"^demo:[A-Za-z0-9_.-]{1,128}$")
DEMO_EVENT_ACTIONS = {
    "start": "demo_start",
    "connected": "demo_connection",
    "expired": "demo_expiry",
    "failed": "demo_failure",
    "disconnected": "demo_disconnect",
}
GUACAMOLE_TEMP_USER_CLEANUP_ENABLED = os.getenv(
    "GUACAMOLE_TEMP_USER_CLEANUP_ENABLED",
    "true",
).strip().lower() not in ("false", "0", "no", "off")
GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS = max(
    60,
    int(os.getenv("GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS", "900")),
)
GUACAMOLE_PROVISIONER_TOKEN = (
    _env_or_secret_file("GUACAMOLE_PROVISIONER_TOKEN") or
    _env_or_secret_file("LAB_MANAGER_TOKEN") or
    ""
)
GUACAMOLE_PROVISIONER_TOKEN_HEADER = os.getenv(
    "GUACAMOLE_PROVISIONER_TOKEN_HEADER",
    "X-Guacamole-Provisioner-Token",
)
DEFAULT_LABSTATION_EXE = r"C:\LabStation\LabStation.exe"
WINRM_READ_TIMEOUT = int(os.getenv("OPS_WINRM_READ_TIMEOUT", "30"))
WINRM_OPERATION_TIMEOUT = int(os.getenv("OPS_WINRM_OPERATION_TIMEOUT", "20"))
WINRM_PORT = 5986
WINRM_ALLOWED_TRANSPORTS = {
    value.strip().lower()
    for value in os.getenv("WINRM_ALLOWED_TRANSPORTS", "ntlm,kerberos,credssp").split(",")
    if value.strip()
}
WINRM_MANAGEMENT_CIDRS = [
    value.strip()
    for value in os.getenv("WINRM_MANAGEMENT_CIDRS", "").split(",")
    if value.strip()
]
ALLOWED_WINRM_COMMANDS = {
    cmd.strip()
    for cmd in os.getenv(
        "OPS_ALLOWED_COMMANDS",
        "prepare-session,release-session,power,session,energy,status-json,recovery,account,service,wol,status",
    ).split(",")
    if cmd.strip()
}

TIMELINE_MAX_LIMIT = max(1, int(os.getenv("OPS_TIMELINE_MAX_OPS", "500")))
TIMELINE_DEFAULT_LIMIT = max(1, min(int(os.getenv("OPS_TIMELINE_DEFAULT_LIMIT", "100")), TIMELINE_MAX_LIMIT))
TIMELINE_PHASE_LOOKBACK = max(TIMELINE_MAX_LIMIT, int(os.getenv("OPS_TIMELINE_PHASE_LOOKBACK", "500")))
NOTIFICATION_SERVICE_URL = os.getenv(
    "NOTIFICATION_SERVICE_URL",
    os.getenv("BLOCKCHAIN_SERVICES_NOTIFICATION_URL", "http://blockchain-services:8080/billing/admin/notifications/send")
)
NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER = os.getenv("NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER", "X-Access-Token")
NOTIFICATION_SERVICE_ACCESS_TOKEN = (
    _env_or_secret_file("NOTIFICATION_SERVICE_ACCESS_TOKEN") or
    _env_or_secret_file("ADMIN_ACCESS_TOKEN")
)
NOTIFICATION_SERVICE_ENABLED = os.getenv("NOTIFICATION_SERVICE_ENABLED", "true").strip().lower() not in ("false", "0", "no", "off")
NOTIFICATION_SERVICE_RETRY_ATTEMPTS = max(0, int(os.getenv("NOTIFICATION_SERVICE_RETRY_ATTEMPTS", "3")))
NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS = max(1, int(os.getenv("NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS", "5")))
def _is_lite_gateway() -> bool:
    issuer = (os.getenv("ISSUER") or "").strip().rstrip("/")
    if not issuer:
        return False
    server_name = (os.getenv("SERVER_NAME") or "localhost").strip()
    https_port = (os.getenv("HTTPS_PORT") or "443").strip()
    local_issuer = f"https://{server_name}{'' if https_port == '443' else ':' + https_port}/auth"
    return issuer != local_issuer.rstrip("/")


ACCESS_AUDIT_URL = os.getenv("ACCESS_AUDIT_URL", "").strip()
if not ACCESS_AUDIT_URL and not _is_lite_gateway():
    ACCESS_AUDIT_URL = "http://blockchain-services:8080/access-audit/internal/session-observed"
SESSION_OBSERVER_GATEWAY_ID = os.getenv("SESSION_OBSERVER_GATEWAY_ID", "").strip()
SESSION_OBSERVER_SIGNING_SECRET = _env_or_secret_file("SESSION_OBSERVER_SIGNING_SECRET").strip()
SESSION_OBSERVATION_OUTBOX_ENABLED = os.getenv(
    "SESSION_OBSERVATION_OUTBOX_ENABLED", "true"
).strip().lower() not in ("false", "0", "no", "off")
SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS = max(
    1, int(os.getenv("SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS", "5"))
)
SESSION_OBSERVATION_OUTBOX_BATCH_SIZE = max(
    1, int(os.getenv("SESSION_OBSERVATION_OUTBOX_BATCH_SIZE", "20"))
)
SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS = max(
    1, int(os.getenv("SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS", "20"))
)
SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS = max(
    1, int(os.getenv("SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS", "5"))
)
SESSION_OBSERVATION_INGEST_TOKEN = _env_or_secret_file("SESSION_OBSERVATION_INGEST_TOKEN")
# The Ops Worker is intentionally not a public API.  OpenResty authenticates
# the operator at the edge and injects this separate, gateway-local credential
# before proxying to the worker.  Direct callers (including other containers)
# must still present it; an absent configuration fails closed rather than
# silently reverting to network-based trust.
OPS_INTERNAL_AUTH_TOKEN = _env_or_secret_file("OPS_INTERNAL_AUTH_TOKEN").strip()
OPS_INTERNAL_AUTH_HEADER = os.getenv(
    "OPS_INTERNAL_AUTH_HEADER",
    "X-Ops-Internal-Token",
).strip()
GUAC_ADMIN_USER = os.getenv("GUAC_ADMIN_USER", "")
GUAC_ADMIN_PASS = _env_or_secret_file("GUAC_ADMIN_PASS")
GUAC_API_URL = os.getenv("GUAC_API_URL", "http://guacamole:8080/guacamole/api").rstrip("/")
GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS = max(
    1, int(os.getenv("GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS", "10"))
)
GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS = max(
    1, int(os.getenv("GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS", "20"))
)
GUACAMOLE_HISTORY_LOOKBACK_SECONDS = max(
    0, int(os.getenv("GUACAMOLE_HISTORY_LOOKBACK_SECONDS", "30"))
)
GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS = max(
    0, int(os.getenv("GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS", "300"))
)
HEARTBEAT_SSE_INTERVAL_SECONDS = max(1, int(os.getenv("OPS_HEARTBEAT_SSE_INTERVAL_SECONDS", "10")))
DISCOVERY_TIMEOUT_SECONDS = max(0.2, float(os.getenv("OPS_DISCOVERY_TIMEOUT_SECONDS", "1.5")))
DISCOVERY_LABSTATION_PORTS = [
    int(port.strip())
    for port in os.getenv("OPS_DISCOVERY_LABSTATION_PORTS", "8765,8088").split(",")
    if port.strip().isdigit()
]
DISCOVERY_LABSTATION_PATHS = [
    path.strip() if path.strip().startswith("/") else f"/{path.strip()}"
    for path in os.getenv("OPS_DISCOVERY_LABSTATION_PATHS", "/labstation/health,/health").split(",")
    if path.strip()
]
DISCOVERY_HEARTBEAT_PATHS = [
    path.strip()
    for path in os.getenv(
        "OPS_DISCOVERY_HEARTBEAT_PATHS",
        r"C:\LabStation\labstation\data\telemetry\heartbeat.json",
    ).split(",")
    if path.strip()
]
HTTP_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
HOST_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
WINRM_TRUST_REF_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")
MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([-:])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$")
GUAC_SELECTOR_RE = re.compile(r"^guac:id:([1-9][0-9]*)$")
ENOUGH_DISCOVERY_SIGNALS = {"labstation-detected", "winrm-reachable"}
HOSTS_LOCK = RLock()
_FERNET: Optional[Fernet] = None

if not HTTP_HEADER_NAME_RE.fullmatch(OPS_INTERNAL_AUTH_HEADER):
    logging.error("Invalid OPS_INTERNAL_AUTH_HEADER; using X-Ops-Internal-Token")
    OPS_INTERNAL_AUTH_HEADER = "X-Ops-Internal-Token"


def _requires_ops_internal_auth(path: str) -> bool:
    """Return whether *path* is an Ops API that only OpenResty may invoke."""
    return path.startswith("/api/") or path.startswith("/aas-admin/")


@APP.before_request
def require_ops_internal_auth():
    if not _requires_ops_internal_auth(request.path):
        return None

    if not OPS_INTERNAL_AUTH_TOKEN:
        logging.error("OPS_INTERNAL_AUTH_TOKEN is not configured; rejecting Ops API request")
        return jsonify({"success": False, "error": "Ops internal authentication is not configured"}), 503

    provided = request.headers.get(OPS_INTERNAL_AUTH_HEADER, "")
    if not provided or not hmac.compare_digest(provided, OPS_INTERNAL_AUTH_TOKEN):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return None


def read_hosts_config(path: str, missing_ok: bool = True) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        if not missing_ok:
            logging.warning("Config file %s not found, continuing with empty host list", path)
        return {"hosts": []}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"hosts": []}
    if not isinstance(data.get("hosts"), list):
        data["hosts"] = []
    return data


def merge_host_configs(base: Dict[str, Any], dynamic: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Dict[str, Any]] = {}
    for source in (base, dynamic):
        for host in source.get("hosts", []):
            if not isinstance(host, dict):
                continue
            name = str(host.get("name") or "").strip()
            if not name:
                continue
            merged[name.lower()] = dict(host)
    return {"hosts": list(merged.values())}


def _load_fernet() -> Fernet:
    global _FERNET  # pylint: disable=global-statement
    if _FERNET:
        return _FERNET
    key = _env_or_secret_file("OPS_SECRETS_KEY").strip()
    if not key:
        raise RuntimeError("OPS_SECRETS_KEY is required to encrypt WinRM credentials")
    _FERNET = Fernet(key.encode("ascii"))
    return _FERNET


def normalize_credential_ref(value: Any) -> str:
    return str(value or "").strip().lower()


def credential_ref_for_host(host: Dict[str, Any]) -> str:
    return normalize_credential_ref(host.get("credential_ref") or host.get("address") or host.get("name"))


def read_winrm_credentials_store() -> Dict[str, Any]:
    if not os.path.exists(OPS_CREDENTIALS_PATH):
        return {"credentials": {}}
    with open(OPS_CREDENTIALS_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"credentials": {}}
    if not isinstance(data.get("credentials"), dict):
        data["credentials"] = {}
    return data


def write_winrm_credentials_store(data: Dict[str, Any]) -> None:
    directory = os.path.dirname(OPS_CREDENTIALS_PATH) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{OPS_CREDENTIALS_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, OPS_CREDENTIALS_PATH)
    try:
        os.chmod(OPS_CREDENTIALS_PATH, 0o600)
    except OSError:
        # Permission hardening is best-effort on bind mounts and Windows filesystems.
        pass


def save_winrm_credentials(credential_ref: str, user: str, password: str) -> None:
    ref = normalize_credential_ref(credential_ref)
    if not ref:
        raise ValueError("credentialRef is required")
    if not str(user or "").strip():
        raise ValueError("user is required")
    if not str(password or "").strip():
        raise ValueError("password is required")
    token = _load_fernet().encrypt(json.dumps({
        "user": str(user).strip(),
        "password": str(password),
    }).encode("utf-8")).decode("ascii")
    data = read_winrm_credentials_store()
    data["credentials"][ref] = {"token": token}
    write_winrm_credentials_store(data)


def load_winrm_credentials(credential_ref: str) -> Optional[Dict[str, str]]:
    ref = normalize_credential_ref(credential_ref)
    if not ref:
        return None
    entry = read_winrm_credentials_store().get("credentials", {}).get(ref)
    if not isinstance(entry, dict) or not entry.get("token"):
        return None
    try:
        raw = _load_fernet().decrypt(str(entry["token"]).encode("ascii"))
        parsed = json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        logging.warning(
            "Unable to decrypt WinRM credential ref %s: %s",
            str(ref).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )
        return None
    user = str(parsed.get("user") or "").strip()
    password = str(parsed.get("password") or "")
    if not user or not password:
        return None
    return {"user": user, "password": password}


def winrm_credentials_configured(credential_ref: str) -> bool:
    return load_winrm_credentials(credential_ref) is not None


WINRM_TRUST_CERTIFICATE_NAME = "server.cer"
WINRM_TRUST_PEM_NAME = "server.pem"
WINRM_TRUST_METADATA_NAME = "metadata.json"
WINRM_CERTIFICATE_MAX_BYTES = _WINRM_CERTIFICATE_MAX_BYTES_DEFAULT
WINRM_CERTIFICATE_EXTENSIONS = {".cer", ".crt", ".der", ".pem"}


def normalize_winrm_trust_ref(value: Any) -> str:
    """Return a safe, case-insensitive directory identifier for Station trust."""
    raw_ref = str(value or "").strip().lower()
    # secure_filename removes path separators and traversal markers. Reject a
    # changed value instead of silently mapping two hosts to one trust store.
    ref = secure_filename(raw_ref)
    if ref != raw_ref or ".." in raw_ref or not WINRM_TRUST_REF_RE.fullmatch(ref):
        raise ValueError("winrm_trust_ref must contain only letters, numbers, dots, underscores, and hyphens")
    return ref


def winrm_trust_ref_for_host(host: Dict[str, Any]) -> str:
    return normalize_winrm_trust_ref(
        host.get("winrm_trust_ref") or host.get("name") or host.get("address")
    )


def _winrm_trust_root() -> str:
    root = os.path.realpath(os.path.abspath(OPS_WINRM_TRUST_PATH))
    if not root:
        raise WinRMTrustError("WINRM_TRUST_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE)
    return root


def _winrm_trust_file_path(host: Dict[str, Any], filename: str) -> str:
    return _resolve_winrm_trust_file_path(
        _winrm_trust_root(),
        winrm_trust_ref_for_host(host),
        filename,
    )


def winrm_trust_certificate_path(host: Dict[str, Any]) -> str:
    """Return the managed certificate path for a host without accepting a user path."""
    return _winrm_trust_file_path(host, WINRM_TRUST_CERTIFICATE_NAME)


def winrm_trust_pem_path(host: Dict[str, Any]) -> str:
    """Return the generated PEM trust path consumed by Requests/OpenSSL."""
    return _winrm_trust_file_path(host, WINRM_TRUST_PEM_NAME)


def _parse_winrm_certificate(path: str) -> x509.Certificate:
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise WinRMTrustError("WINRM_TRUST_REQUIRED", WINRM_TRUST_REQUIRED_MESSAGE) from exc
    if size <= 0 or size > WINRM_CERTIFICATE_MAX_BYTES:
        raise WinRMTrustError("WINRM_TRUST_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE)
    try:
        with open(path, "rb") as handle:
            raw = handle.read(WINRM_CERTIFICATE_MAX_BYTES + 1)
    except OSError as exc:
        raise WinRMTrustError("WINRM_TRUST_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE) from exc
    if len(raw) > WINRM_CERTIFICATE_MAX_BYTES:
        raise WinRMTrustError("WINRM_TRUST_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE)

    return _parse_winrm_certificate_bytes(raw)


def _parse_winrm_certificate_bytes(raw: bytes) -> x509.Certificate:
    """Preserve the worker entrypoint while delegating bounded parsing."""
    return _parse_winrm_certificate_bytes_impl(raw, max_bytes=WINRM_CERTIFICATE_MAX_BYTES)


def _winrm_trust_metadata_path(host: Dict[str, Any]) -> str:
    return _winrm_trust_file_path(host, WINRM_TRUST_METADATA_NAME)


def _write_winrm_trust_bytes(path: str, content: bytes) -> None:
    """Preserve the worker entrypoint while delegating atomic persistence."""
    _write_trust_bytes_impl(path, content)


def _read_winrm_trust_metadata(host: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _read_trust_metadata_file(_winrm_trust_metadata_path(host))


def _write_winrm_trust_metadata(host: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    _write_trust_metadata_file(
        _winrm_trust_metadata_path(host),
        metadata,
        write_bytes=_write_winrm_trust_bytes,
    )


def _validate_winrm_certificate(certificate: x509.Certificate, host: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve the worker entrypoint while delegating certificate validation."""
    return _validate_winrm_certificate_impl(
        certificate,
        host,
        winrm_trust_ref_for_host(host),
        certificate_matches_host=_certificate_matches_host,
        certificate_metadata=_winrm_certificate_metadata,
        trust_error_messages=WINRM_TRUST_ERROR_MESSAGES,
        invalid_message=WINRM_CERTIFICATE_INVALID_MESSAGE,
    )


def _read_winrm_certificate_upload() -> bytes:
    """Read an operator upload without accepting paths or unbounded request data."""
    uploaded = request.files.get("certificate") or request.files.get("file")
    if uploaded is not None:
        filename = str(uploaded.filename or "").strip()
        if filename:
            extension = os.path.splitext(secure_filename(filename))[1].lower()
            if extension not in WINRM_CERTIFICATE_EXTENSIONS:
                raise WinRMTrustError("WINRM_CERTIFICATE_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE)
        raw = uploaded.stream.read(WINRM_CERTIFICATE_MAX_BYTES + 1)
    else:
        if request.content_length and request.content_length > WINRM_CERTIFICATE_MAX_BYTES:
            raise WinRMTrustError("WINRM_TRUST_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE)
        raw = request.get_data(cache=False, as_text=False)
    if not raw:
        raise WinRMTrustError("WINRM_CERTIFICATE_REQUIRED", WINRM_CERTIFICATE_REQUIRED_MESSAGE)
    if len(raw) > WINRM_CERTIFICATE_MAX_BYTES:
        raise WinRMTrustError("WINRM_TRUST_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE)
    return raw


def _winrm_trust_request_value(name: str) -> str:
    value = request.form.get(name)
    if value is not None:
        return str(value).strip()
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        return str(payload.get(name) or "").strip()
    return ""


def _winrm_certificate_response_metadata(
    certificate: x509.Certificate,
    host: Dict[str, Any],
    input_format: str,
) -> Dict[str, Any]:
    metadata = _winrm_certificate_metadata(certificate, winrm_trust_ref_for_host(host))
    metadata["host"] = host.get("name")
    metadata["address"] = host.get("address")
    metadata["format"] = input_format
    return metadata


def _store_winrm_trust_certificate(
    host: Dict[str, Any],
    certificate: x509.Certificate,
) -> Dict[str, Any]:
    metadata = _winrm_certificate_response_metadata(certificate, host, "DER")
    metadata.update({
        "uploadedAt": _format_certificate_datetime(datetime.now(timezone.utc)),
        "uploadedBy": "lab-manager",
        "source": "lab-manager",
    })
    _write_winrm_trust_bytes(
        winrm_trust_certificate_path(host),
        certificate.public_bytes(serialization.Encoding.DER),
    )
    _write_winrm_trust_metadata(host, metadata)
    _materialize_winrm_pem(host, certificate)
    return inspect_winrm_trust(host)


def _delete_winrm_trust_certificate(host: Dict[str, Any]) -> None:
    _delete_trust_files_impl(
        [
            _winrm_trust_file_path(host, WINRM_TRUST_CERTIFICATE_NAME),
            _winrm_trust_file_path(host, WINRM_TRUST_PEM_NAME),
            _winrm_trust_file_path(host, WINRM_TRUST_METADATA_NAME),
        ]
    )


def _materialize_winrm_pem(host: Dict[str, Any], certificate: x509.Certificate) -> str:
    """Preserve the worker entrypoint while delegating PEM materialization."""
    return _materialize_trust_pem_impl(
        winrm_trust_pem_path(host),
        certificate,
        max_bytes=WINRM_CERTIFICATE_MAX_BYTES,
    )


def inspect_winrm_trust(host: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve the worker entrypoint while delegating trust inspection."""
    return _inspect_winrm_trust_impl(
        host,
        trust_ref_for_host=winrm_trust_ref_for_host,
        certificate_path_for_host=winrm_trust_certificate_path,
        is_file=os.path.isfile,
        parse_certificate=_parse_winrm_certificate,
        materialize_pem=_materialize_winrm_pem,
        certificate_metadata=_winrm_certificate_metadata,
        read_metadata=_read_winrm_trust_metadata,
        validate_certificate=_validate_winrm_certificate,
        format_datetime=_format_certificate_datetime,
        now=lambda: datetime.now(timezone.utc),
        trust_error_type=WinRMTrustError,
    )


def load_winrm_trust(host: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Preserve the worker entrypoint while delegating trust loading."""
    return _load_winrm_trust_impl(
        host,
        inspect_trust=inspect_winrm_trust,
        pem_path_for_host=winrm_trust_pem_path,
        required_code=WINRM_TRUST_REQUIRED_CODE,
        required_message=WINRM_TRUST_REQUIRED_MESSAGE,
        expired_message=WINRM_CERTIFICATE_EXPIRED_MESSAGE,
        not_yet_valid_message=WINRM_CERTIFICATE_NOT_YET_VALID_MESSAGE,
        trust_error_messages=WINRM_TRUST_ERROR_MESSAGES,
        invalid_message=WINRM_CERTIFICATE_INVALID_MESSAGE,
    )


def refresh_winrm_trust_store(hosts: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Preserve the worker entrypoint while delegating trust refresh."""
    return _refresh_winrm_trust_store_impl(
        hosts,
        _winrm_trust_root(),
        trust_ref_for_host=winrm_trust_ref_for_host,
        inspect_trust=inspect_winrm_trust,
        sanitize_log_value=_sanitize_log_value,
        logger=logging,
    )


def resolve_host_secret_refs(raw: Dict[str, Any]) -> Dict[str, Any]:
    # Host catalogs contain references only. Credentials are resolved from the
    # encrypted store at operation time and never copied into the catalog.
    for host in raw.get("hosts", []):
        if not host.get("credential_ref"):
            host["credential_ref"] = host.get("address") or host.get("name")
        host.pop("winrm_user", None)
        host.pop("winrm_pass", None)
        if not winrm_credentials_configured(credential_ref_for_host(host)):
            logging.warning("Missing WinRM credentials for host %s", host.get("name", "<unknown>"))
    return raw


def _catalog_bool(value: Any) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes", "on"):
        return True
    if normalized in ("false", "0", "no", "off"):
        return False
    raise ValueError("winrm_use_ssl must be a boolean")


def _resolved_addresses(address: str) -> List[Any]:
    try:
        return [ipaddress.ip_address(address)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(address, None, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError(f"address '{address}' cannot be resolved") from exc
        resolved = {ipaddress.ip_address(info[4][0]) for info in infos}
        if not resolved:
            raise ValueError(f"address '{address}' cannot be resolved")
        return list(resolved)


def validate_winrm_catalog(config: Dict[str, Any]) -> None:
    return _validate_winrm_catalog_impl(
        config,
        management_cidrs=WINRM_MANAGEMENT_CIDRS,
        winrm_port=WINRM_PORT,
        catalog_bool=_catalog_bool,
        resolve_addresses=_resolved_addresses,
        trust_ref_pattern=WINRM_TRUST_REF_RE,
    )

def load_config() -> Dict[str, Any]:
    return _load_host_config_impl(
        CONFIG_PATH,
        DYNAMIC_CONFIG_PATH,
        read_config=read_hosts_config,
        merge_configs=merge_host_configs,
        validate_config=validate_winrm_catalog,
        resolve_secret_refs=resolve_host_secret_refs,
    )


HOSTS = HostRegistry(load_config())


def build_ops_dsn() -> Optional[str]:
    return _build_ops_dsn_impl(
        MYSQL_DSN,
        OPS_MYSQL_USER,
        OPS_MYSQL_PASSWORD,
        OPS_MYSQL_DATABASE,
        MYSQL_HOSTNAME,
        MYSQL_PORT,
        create_url=URL.create,
    )


OPS_DSN = build_ops_dsn()
DB_ENGINE: Optional[Engine] = create_engine(OPS_DSN, pool_pre_ping=True) if OPS_DSN else None


def build_guacamole_dsn() -> Optional[str]:
    return _build_guacamole_dsn_impl(
        GUACAMOLE_MYSQL_DSN,
        GUACAMOLE_MYSQL_USER,
        GUACAMOLE_MYSQL_PASSWORD,
        GUACAMOLE_MYSQL_DATABASE,
        MYSQL_DSN,
        MYSQL_HOSTNAME,
        MYSQL_PORT,
        create_url=URL.create,
        parse_url=make_url,
        logger=logging,
    )


GUACAMOLE_DSN = build_guacamole_dsn()
GUACAMOLE_DB_ENGINE: Optional[Engine] = (
    create_engine(GUACAMOLE_DSN, pool_pre_ping=True) if GUACAMOLE_DSN else None
)


def to_utc(ts: Any) -> Optional[datetime]:
    return _to_utc_impl(
        ts,
        parse_datetime=datetime.fromisoformat,
        utc_timezone=timezone.utc,
    )


def wol_and_wait(mac: str, broadcast: Optional[str], port: int, ping_target: str,
                 attempts: int, wait_seconds: float, probe_port: Optional[int] = None) -> Tuple[bool, int]:
    for attempt in range(1, attempts + 1):
        send_magic_packet(mac, ip_address=broadcast or "255.255.255.255", port=port)
        time.sleep(wait_seconds)
        if host_is_up(ping_target, wait_seconds, probe_port=probe_port):
            return True, attempt
    return False, attempts


def host_is_up(target: str, timeout: float, probe_port: Optional[int] = None) -> bool:
    if not target:
        return False
    target = str(target).strip()
    if not _is_valid_ping_target(target):
        logging.warning("Invalid reachability target rejected")
        return False

    # The worker runs in a container and the Lab Station exposes WinRM.  A
    # direct TCP probe keeps the reachability check in-process and avoids
    # passing request data to a shell command.  The port is controlled by the
    # Lab Station exposes only the canonical HTTPS WinRM listener.
    if probe_port is None:
        probe_port = WINRM_PORT
    if probe_port != WINRM_PORT:
        logging.warning("Invalid reachability port rejected")
        return False
    try:
        with socket.create_connection((target, probe_port), timeout=max(float(timeout), 0.1)):
            return True
    except (OSError, ValueError, TypeError):
        # A failed reachability probe is represented by False.
        pass
    return False


def _coerce_bool(value: Any) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes", "on"):
        return True
    if normalized in ("false", "0", "no", "off"):
        return False
    raise ValueError("WinRM use_ssl must be a boolean")


def _winrm_connection_policy(
    host: Dict[str, Any],
    use_ssl: Optional[bool],
    port: Optional[int],
    transport: Optional[str],
) -> Tuple[bool, int, str]:
    return _resolve_winrm_connection_policy_impl(
        host,
        use_ssl,
        port,
        transport,
        winrm_port=WINRM_PORT,
        allowed_transports=WINRM_ALLOWED_TRANSPORTS,
        coerce_bool=_coerce_bool,
    )


def _winrm_credentials(host: Dict[str, Any], user: Optional[str], password: Optional[str]) -> Tuple[str, str]:
    return _resolve_winrm_credentials_impl(
        host,
        user,
        password,
        credential_ref_for_host=credential_ref_for_host,
        load_credentials=load_winrm_credentials,
        required_message=WINRM_CREDENTIALS_REQUIRED_MESSAGE,
    )


def _winrm_trust_error_payload(host_name: Any, code: str) -> Dict[str, Any]:
    code = code if code in WINRM_TRUST_ERROR_MESSAGES else "WINRM_TRUST_INVALID"
    return {
        "error": WINRM_TRUST_ERROR_MESSAGES[code],
        "code": code,
        "host": host_name,
        "requestId": _request_id(),
    }


def create_winrm_session(
    host: Dict[str, Any],
    user: str,
    password: str,
    transport: str,
    effective_port: int,
    *,
    read_timeout_sec: Optional[int] = None,
    operation_timeout_sec: Optional[int] = None,
):
    """Create a validated HTTPS WinRM session using trust for this host only."""
    return _create_winrm_session_impl(
        host,
        user,
        password,
        transport,
        effective_port,
        read_timeout_sec=read_timeout_sec,
        operation_timeout_sec=operation_timeout_sec,
        load_trust=load_winrm_trust,
        session_factory=winrm.Session,
    )


def run_winrm_method(session: Any, method_name: str, *args: Any):
    """Run a WinRM operation while keeping TLS failures actionable and stable."""
    return _run_winrm_method_impl(
        session,
        method_name,
        *args,
        ssl_error_type=requests.exceptions.SSLError,
        trust_error_factory=WinRMTrustError,
        tls_error_code="WINRM_TLS_FAILED",
        tls_error_message=WINRM_TLS_FAILED_MESSAGE,
    )


def winrm_endpoint(host: Dict[str, Any], use_ssl: Optional[bool], port: Optional[int]) -> str:
    return _build_winrm_endpoint_impl(
        host,
        use_ssl,
        port,
        resolve_policy=_winrm_connection_policy,
    )


def run_labstation_command(host: Dict[str, Any], command: str, args: Optional[list],
                           user: Optional[str], password: Optional[str],
                           transport: Optional[str], use_ssl: Optional[bool],
                           port: Optional[int]) -> Dict[str, Any]:
    return _run_labstation_command_impl(
        host,
        command,
        args,
        user,
        password,
        transport,
        use_ssl,
        port,
        resolve_credentials=_winrm_credentials,
        resolve_policy=_winrm_connection_policy,
        create_session=create_winrm_session,
        run_method=run_winrm_method,
        build_command=_build_labstation_command_impl,
        default_executable=DEFAULT_LABSTATION_EXE,
        read_timeout_sec=WINRM_READ_TIMEOUT,
        operation_timeout_sec=WINRM_OPERATION_TIMEOUT,
        logger=logging,
        clock=time.time,
    )


def run_remote_powershell(host: Dict[str, Any], script: str, user: Optional[str], password: Optional[str],
                          transport: Optional[str], use_ssl: Optional[bool], port: Optional[int]) -> str:
    return _run_remote_powershell_impl(
        host,
        script,
        user,
        password,
        transport,
        use_ssl,
        port,
        resolve_credentials=_winrm_credentials,
        resolve_policy=_winrm_connection_policy,
        create_session=create_winrm_session,
        run_method=run_winrm_method,
        read_timeout_sec=WINRM_READ_TIMEOUT,
        operation_timeout_sec=WINRM_OPERATION_TIMEOUT,
    )


def read_remote_file(host: Dict[str, Any], path: str, user: Optional[str], password: Optional[str],
                     transport: Optional[str], use_ssl: Optional[bool], port: Optional[int]) -> str:
    return _read_remote_file_impl(
        host,
        path,
        user,
        password,
        transport,
        use_ssl,
        port,
        resolve_credentials=_winrm_credentials,
        resolve_policy=_winrm_connection_policy,
        create_session=create_winrm_session,
        run_method=run_winrm_method,
        build_command=_build_read_remote_file_command_impl,
        read_timeout_sec=WINRM_READ_TIMEOUT,
        operation_timeout_sec=WINRM_OPERATION_TIMEOUT,
    )


def write_remote_file(host: Dict[str, Any], path: str, contents: str,
                      user: Optional[str], password: Optional[str],
                      transport: Optional[str], use_ssl: Optional[bool], port: Optional[int]) -> None:
    return _write_remote_file_impl(
        host,
        path,
        contents,
        user,
        password,
        transport,
        use_ssl,
        port,
        resolve_credentials=_winrm_credentials,
        resolve_policy=_winrm_connection_policy,
        create_session=create_winrm_session,
        run_method=run_winrm_method,
        build_command=_build_write_remote_file_command_impl,
        read_timeout_sec=WINRM_READ_TIMEOUT,
        operation_timeout_sec=WINRM_OPERATION_TIMEOUT,
    )


def remove_remote_file(host: Dict[str, Any], path: str,
                       user: Optional[str], password: Optional[str],
                       transport: Optional[str], use_ssl: Optional[bool], port: Optional[int]) -> None:
    return _remove_remote_file_impl(
        host,
        path,
        user,
        password,
        transport,
        use_ssl,
        port,
        resolve_credentials=_winrm_credentials,
        resolve_policy=_winrm_connection_policy,
        create_session=create_winrm_session,
        run_method=run_winrm_method,
        build_command=_build_remove_remote_file_command_impl,
        read_timeout_sec=WINRM_READ_TIMEOUT,
        operation_timeout_sec=WINRM_OPERATION_TIMEOUT,
    )


def get_local_mode_flag_path(host: Dict[str, Any]) -> str:
    return host.get("local_mode_flag_path", r"C:\LabStation\labstation\data\local-mode.flag")


def persist_heartbeat(engine: Engine, host: Dict[str, Any], heartbeat: Dict[str, Any],
                      last_event: Optional[Dict[str, Any]]) -> None:
    ts = to_utc(heartbeat.get("timestamp")) or datetime.now(timezone.utc)
    ready = heartbeat.get("summary", {}).get("ready")
    status = heartbeat.get("status", {})
    operations = heartbeat.get("operations", {})

    last_forced = operations.get("lastForcedLogoff") or {}
    last_power = operations.get("lastPowerAction") or {}
    local_mode = status.get("localModeEnabled")
    local_session = status.get("localSessionActive")

    last_forced_ts = to_utc(last_forced.get("timestamp"))
    last_power_ts = to_utc(last_power.get("timestamp"))

    with engine.begin() as conn:
        host_row = conn.execute(
            text("SELECT id FROM lab_hosts WHERE name=:name"),
            {"name": host.get("name")},
        ).fetchone()
        if host_row:
            host_id = host_row[0]
            conn.execute(
                text("UPDATE lab_hosts SET address=:address, mac=:mac, last_seen=:last_seen WHERE id=:id"),
                {
                    "address": host.get("address"),
                    "mac": host.get("mac"),
                    "last_seen": ts,
                    "id": host_id,
                },
            )
        else:
            res = conn.execute(
                text("INSERT INTO lab_hosts (name, address, mac, last_seen) VALUES (:name, :address, :mac, :last_seen)"),
                {
                    "name": host.get("name"),
                    "address": host.get("address"),
                    "mac": host.get("mac"),
                    "last_seen": ts,
                },
            )
            host_id = res.lastrowid

        conn.execute(
            text(
                """
                INSERT INTO lab_host_heartbeat (
                    host_id, timestamp_utc, ready, local_mode, local_session,
                    last_forced_logoff_ts, last_forced_logoff_user,
                    last_power_action_ts, last_power_action_mode,
                    raw_json
                ) VALUES (
                    :host_id, :ts, :ready, :local_mode, :local_session,
                    :last_forced_ts, :last_forced_user,
                    :last_power_ts, :last_power_mode,
                    :raw_json
                )
                """
            ),
            {
                "host_id": host_id,
                "ts": ts,
                "ready": ready,
                "local_mode": local_mode,
                "local_session": local_session,
                "last_forced_ts": last_forced_ts,
                "last_forced_user": last_forced.get("user"),
                "last_power_ts": last_power_ts,
                "last_power_mode": last_power.get("mode"),
                "raw_json": json.dumps(heartbeat),
            },
        )

        if last_event:
            conn.execute(
                text(
                    """
                    INSERT INTO lab_host_events (host_id, kind, timestamp_utc, payload)
                    VALUES (:host_id, :kind, :ts, :payload)
                    """
                ),
                {
                    "host_id": host_id,
                    "kind": "session-guard",
                    "ts": to_utc(last_event.get("timestamp")) or ts,
                    "payload": json.dumps(last_event),
                },
            )


def parse_bool(value: Any, default: bool) -> bool:
    return _parse_bool_impl(value, default)


def normalize_args(args: Any, default: Optional[List[str]] = None) -> List[str]:
    return _normalize_args_impl(args, default)


def parse_recipients(value: Any, default: Optional[List[str]] = None) -> List[str]:
    return _parse_recipients_impl(value, default)


NOTIFICATION_SERVICE_RECIPIENTS = parse_recipients(os.getenv("NOTIFICATION_SERVICE_RECIPIENTS"))

OPS_ALERT_FAILURE_THRESHOLD = max(1, int(os.getenv("OPS_ALERT_FAILURE_THRESHOLD", "3")))
OPS_ALERT_WINDOW_SECONDS = max(60, int(os.getenv("OPS_ALERT_WINDOW_SECONDS", "300")))
OPS_ALERT_COOLDOWN_SECONDS = max(60, int(os.getenv("OPS_ALERT_COOLDOWN_SECONDS", "900")))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def record_reservation_operation(
    reservation_id: str,
    lab_id: Optional[str],
    host_name: str,
    action: str,
    status: str,
    success: bool,
    response_code: Optional[int] = None,
    duration_ms: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
):
    if not DB_ENGINE:
        return
    created_at = _now_utc()
    try:
        with DB_ENGINE.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO reservation_operations (
                        reservation_id, lab_id, host, action, status, success,
                        response_code, duration_ms, payload, message, created_at
                    ) VALUES (
                        :reservation_id, :lab_id, :host, :action, :status, :success,
                        :response_code, :duration_ms, :payload, :message, :created_at
                    )
                    """
                ),
                {
                    "reservation_id": reservation_id,
                    "lab_id": lab_id,
                    "host": host_name,
                    "action": action,
                    "status": status,
                    "success": success,
                    "response_code": response_code,
                    "duration_ms": duration_ms,
                    "payload": json.dumps(payload) if payload is not None else None,
                    "message": message,
                    "created_at": created_at,
                },
            )
        if not success and action not in ("notification", "alert"):
            try:
                _check_failure_alert(host_name, reservation_id, lab_id, action, message, payload)
            except Exception as exc:
                logging.warning(
                    "Failure alert check failed for %s: %s",
                    str(host_name).replace("\r", "\\r").replace("\n", "\\n"),
                    type(exc).__name__,
                )
    except Exception as exc:
        logging.error(
            "Failed to persist reservation operation %s/%s: %s",
            str(reservation_id).replace("\r", "\\r").replace("\n", "\\n"),
            str(action).replace("\r", "\\r").replace("\n", "\\n"),
            type(exc).__name__,
        )


def _record_power_operation(operation: Dict[str, Any]) -> None:
    """Project a power step into the existing reservation timeline."""
    reservation_id = str(operation.get("reservationId") or "").strip()
    controller_id = str(operation.get("controllerId") or "").strip()
    action = str(operation.get("action") or "").strip().lower()
    if not reservation_id or not controller_id or action not in {"on", "off", "cycle"}:
        logging.warning("Skipping malformed power operation projection")
        return
    status = str(operation.get("status") or "failed")
    success = bool(operation.get("success"))
    record_reservation_operation(
        reservation_id=reservation_id,
        lab_id=str(operation.get("labId")) if operation.get("labId") is not None else None,
        host_name=controller_id,
        action=f"power:{action}",
        status=status,
        success=success,
        response_code=200 if success else 502,
        duration_ms=operation.get("durationMs"),
        payload={
            "phase": operation.get("phase"),
            "controllerId": controller_id,
            "outlet": operation.get("outlet"),
            "idempotencyKey": operation.get("idempotencyKey"),
            "observedStateBefore": operation.get("observedStateBefore"),
            "observedStateAfter": operation.get("observedStateAfter"),
            "actor": operation.get("actor"),
            "reason": operation.get("reason"),
        },
        message=operation.get("message"),
    )


POWER_OPERATION_STORE = PowerOperationStore(DB_ENGINE) if DB_ENGINE else None
POWER_CREDENTIAL_STORE = PowerCredentialStore.from_environment()
APP.extensions["power_credential_store"] = POWER_CREDENTIAL_STORE
try:
    POWER_RUNTIME = PowerRuntime.from_path(
        POWER_CONFIG_PATH,
        record_operation=_record_power_operation,
        operation_store=POWER_OPERATION_STORE,
        credential_resolver=POWER_CREDENTIAL_STORE.get,
        status_cache_ttl_seconds=POWER_STATUS_CACHE_SECONDS,
    )
except Exception as exc:
    # A malformed or unavailable power catalog must fail closed for power
    # operations without preventing unrelated Lab Station operations from
    # starting.
    logging.error("Power configuration unavailable: %s", type(exc).__name__)
    POWER_RUNTIME = PowerRuntime.from_config(
        {"controllers": [], "outlets": [], "policies": []},
        record_operation=_record_power_operation,
        operation_store=POWER_OPERATION_STORE,
        credential_resolver=POWER_CREDENTIAL_STORE.get,
        status_cache_ttl_seconds=POWER_STATUS_CACHE_SECONDS,
    )
APP.extensions["power_runtime"] = POWER_RUNTIME
APP.register_blueprint(power_bp)


def _host_local_mode_enabled(host: Dict[str, Any]) -> bool:
    """Read the last persisted Lab Station local-mode signal when available."""
    if DB_ENGINE:
        try:
            with DB_ENGINE.connect() as conn:
                heartbeat = _fetch_latest_heartbeat(conn, host.get("name", ""))
            if heartbeat is not None:
                return bool(heartbeat.get("localMode"))
        except Exception as exc:
            logging.warning("Unable to read local mode for power policy: %s", type(exc).__name__)
    return parse_bool(host.get("local_mode", host.get("localMode")), False)


def _execute_reservation_power_phase(
    reservation_id: str,
    lab_id: Optional[str],
    host: Dict[str, Any],
    phase: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    if not lab_id or not parse_bool(payload.get("power", True), True):
        return {"success": True, "status": "power_disabled", "phase": phase, "steps": []}
    try:
        return POWER_RUNTIME.execute_policy(
            str(lab_id),
            str(reservation_id),
            phase,
            actor=str(payload.get("actor") or "reservation-orchestrator"),
            local_mode=_host_local_mode_enabled(host),
        )
    except (PowerValidationError, KeyError, PermissionError) as exc:
        logging.warning("Power policy phase failed: %s", type(exc).__name__)
        return {
            "success": False,
            "status": "failed",
            "phase": phase,
            "steps": [],
            "message": "Power policy phase failed",
        }


def _should_send_failure_alert(host_name: str) -> bool:
    if not DB_ENGINE or not host_name:
        return False
    if not NOTIFICATION_SERVICE_ENABLED or not NOTIFICATION_SERVICE_URL:
        return False

    now = _now_utc()
    window_start = now - timedelta(seconds=OPS_ALERT_WINDOW_SECONDS)
    cooldown_start = now - timedelta(seconds=OPS_ALERT_COOLDOWN_SECONDS)

    with DB_ENGINE.begin() as conn:
        failure_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM reservation_operations "
                "WHERE host = :host AND success = 0 "
                "AND action NOT IN ('notification', 'alert') "
                "AND created_at >= :window_start"
            ),
            {"host": host_name, "window_start": window_start},
        ).scalar() or 0

        recent_alert = conn.execute(
            text(
                "SELECT 1 FROM reservation_operations "
                "WHERE host = :host AND action = 'alert' "
                "AND created_at >= :cooldown_start LIMIT 1"
            ),
            {"host": host_name, "cooldown_start": cooldown_start},
        ).scalar()

    return failure_count >= OPS_ALERT_FAILURE_THRESHOLD and recent_alert is None


def _send_failure_alert(
    reservation_id: str,
    lab_id: Optional[str],
    host_name: str,
    failure_reason: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    subject = f"Lab Gateway alert: repeated failures for {host_name}"
    body = [
        f"Reservation: {reservation_id}",
        f"Lab ID: {lab_id or 'unknown'}",
        f"Host: {host_name}",
        f"Condition: {failure_reason}",
    ]
    if details:
        body.append(f"Details: {json.dumps(details, default=str)}")

    recipients = list(NOTIFICATION_SERVICE_RECIPIENTS)
    payload = {
        "recipients": recipients,
        "subject": subject,
        "textBody": "\n".join(body),
        "htmlBody": "<p>" + "</p><p>".join(body) + "</p>",
        "icsContent": None,
        "icsFileName": None,
    }
    headers = {"Content-Type": "application/json"}
    if NOTIFICATION_SERVICE_ACCESS_TOKEN:
        headers[NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER] = NOTIFICATION_SERVICE_ACCESS_TOKEN

    attempt = 0
    response = None
    resp_text = None
    status_code = None
    last_exception: Optional[Exception] = None
    while attempt <= NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
        attempt += 1
        try:
            response = requests.post(NOTIFICATION_SERVICE_URL, json=payload, headers=headers, timeout=10)
            status_code = response.status_code
            resp_text = response.text
            success = response.ok
            if success:
                break
            if attempt > NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
                break
            time.sleep(NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS * attempt)
        except Exception as exc:
            last_exception = exc
            if attempt > NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
                break
            time.sleep(NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS * attempt)

    if response is not None and response.ok:
        record_reservation_operation(
            reservation_id,
            lab_id,
            host_name,
            "alert",
            "completed",
            True,
            response_code=status_code,
            payload={
                "failureReason": failure_reason,
                "attempts": attempt,
                "response": resp_text,
            },
            message=f"Alert sent after {attempt} attempt(s)",
        )
    else:
        record_reservation_operation(
            reservation_id,
            lab_id,
            host_name,
            "alert",
            "failed",
            False,
            response_code=status_code,
            payload={
                "failureReason": failure_reason,
                "attempts": attempt,
                "response": resp_text,
                "exception": str(last_exception) if last_exception else None,
            },
            message=(
                f"Alert failed after {attempt} attempt(s): {resp_text or last_exception}"
            ),
        )


def _check_failure_alert(
    host_name: str,
    reservation_id: str,
    lab_id: Optional[str],
    action: str,
    message: Optional[str],
    payload: Optional[Dict[str, Any]],
) -> None:
    if not _should_send_failure_alert(host_name):
        return

    failure_reason = (
        f"At least {OPS_ALERT_FAILURE_THRESHOLD} failed operations in the last {OPS_ALERT_WINDOW_SECONDS} seconds"
    )
    details = {
        "triggerAction": action,
        "triggerMessage": message,
        "payload": payload,
    }
    _send_failure_alert(reservation_id, lab_id, host_name, failure_reason, details)


def notify_critical_failure(
    reservation_id: str,
    lab_id: Optional[str],
    host_name: str,
    action: str,
    failure_reason: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    if not NOTIFICATION_SERVICE_ENABLED or not NOTIFICATION_SERVICE_URL:
        return

    subject = f"Lab Gateway alert: {action} failed for {host_name}"
    body = [
        f"Reservation: {reservation_id}",
        f"Lab ID: {lab_id or 'unknown'}",
        f"Host: {host_name}",
        f"Action: {action}",
        f"Reason: {failure_reason}",
    ]
    if details:
        body.append(f"Details: {json.dumps(details, default=str)}")

    recipients = list(NOTIFICATION_SERVICE_RECIPIENTS)
    payload = {
        "recipients": recipients,
        "subject": subject,
        "textBody": "\n".join(body),
        "htmlBody": "<p>" + "</p><p>".join(body) + "</p>",
        "icsContent": None,
        "icsFileName": None,
    }
    headers = {"Content-Type": "application/json"}
    if NOTIFICATION_SERVICE_ACCESS_TOKEN:
        headers[NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER] = NOTIFICATION_SERVICE_ACCESS_TOKEN

    attempt = 0
    duration_ms = 0
    response = None
    resp_text = None
    status_code = None
    last_exception: Optional[Exception] = None
    while attempt <= NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
        attempt += 1
        start = time.time()
        try:
            response = requests.post(NOTIFICATION_SERVICE_URL, json=payload, headers=headers, timeout=10)
            status_code = response.status_code
            resp_text = response.text
            success = response.ok
            duration_ms = int((time.time() - start) * 1000)
            if success:
                break
            if attempt > NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
                break
            time.sleep(NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS * attempt)
        except Exception as exc:
            last_exception = exc
            duration_ms = int((time.time() - start) * 1000)
            if attempt > NOTIFICATION_SERVICE_RETRY_ATTEMPTS:
                break
            time.sleep(NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS * attempt)

    if response is not None and response.ok:
        op_payload = {
            "failureAction": action,
            "notificationUrl": NOTIFICATION_SERVICE_URL,
            "attempts": attempt,
            "response": resp_text,
        }
        record_reservation_operation(
            reservation_id,
            lab_id,
            host_name,
            "notification",
            "completed",
            True,
            response_code=status_code,
            duration_ms=duration_ms,
            payload=op_payload,
            message=f"Notification sent after {attempt} attempt(s)",
        )
    else:
        error_details = {
            "failureAction": action,
            "notificationUrl": NOTIFICATION_SERVICE_URL,
            "attempts": attempt,
            "response": "Notification service did not accept the request",
        }
        if last_exception is not None:
            logging.warning(
                "Notification delivery failed for %s/%s: %s",
                str(reservation_id).replace("\r", "\\r").replace("\n", "\\n"),
                str(action).replace("\r", "\\r").replace("\n", "\\n"),
                type(last_exception).__name__,
            )
        record_reservation_operation(
            reservation_id,
            lab_id,
            host_name,
            "notification",
            "failed",
            False,
            response_code=status_code,
            duration_ms=duration_ms,
            payload=error_details,
            message=f"Notification failed after {attempt} attempt(s)",
        )


def perform_wake_step(
    host: Dict[str, Any],
    reservation_id: str,
    lab_id: Optional[str],
    options: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    mac = options.get("mac") or host.get("mac")
    if not mac:
        message = "MAC address not configured"
        record_reservation_operation(reservation_id, lab_id, host.get("name", ""), "wake", "failed", False, message=message)
        return False, {
            "action": "wake",
            "success": False,
            "status": "failed",
            "message": message,
            "details": {}
        }

    ping_target = options.get("ping_target") or host.get("ping_target") or host.get("address")
    if not ping_target:
        message = "Ping target not configured"
        record_reservation_operation(reservation_id, lab_id, host.get("name", ""), "wake", "failed", False, message=message)
        return False, {
            "action": "wake",
            "success": False,
            "status": "failed",
            "message": message,
            "details": {}
        }

    attempts = int(options.get("attempts", host.get("wake_attempts", 3)))
    wait_seconds = float(options.get("ping_timeout", 10))
    broadcast = options.get("broadcast") or host.get("broadcast")
    port = int(options.get("port", host.get("wol_port", 9)))
    configured_probe_port = host.get("winrm_port")
    try:
        probe_port = int(configured_probe_port) if configured_probe_port not in (None, "") else None
    except (TypeError, ValueError):
        probe_port = None

    start = time.time()
    success = False
    used_attempts = 0
    message = ""
    try:
        success, used_attempts = wol_and_wait(
            mac, broadcast, port, ping_target, attempts, wait_seconds, probe_port=probe_port
        )
        message = "Host reachable" if success else "Host did not respond to ping"
    except Exception as exc:
        logging.exception("Wake operation failed for %s", host.get("name"))
        message = "Wake operation failed"
    duration_ms = int((time.time() - start) * 1000)
    status = "completed" if success else "failed"
    details = {
        "mac": mac,
        "pingTarget": ping_target,
        "attemptsRequested": attempts,
        "attemptsUsed": used_attempts,
        "waitSeconds": wait_seconds,
        "port": port,
        "broadcast": broadcast,
    }
    record_reservation_operation(
        reservation_id,
        lab_id,
        host.get("name", ""),
        "wake",
        status,
        success,
        response_code=200 if success else 504,
        duration_ms=duration_ms,
        payload=details,
        message=message,
    )
    if not success:
        notify_critical_failure(reservation_id, lab_id, host.get("name", ""), "wake", message, details)
    return success, {
        "action": "wake",
        "success": success,
        "status": status,
        "message": message,
        "durationMs": duration_ms,
        "details": details,
    }


def perform_command_step(
    host: Dict[str, Any],
    reservation_id: str,
    lab_id: Optional[str],
    action: str,
    command: str,
    args: List[str],
) -> Tuple[bool, Dict[str, Any]]:
    start = time.time()
    success = False
    result: Dict[str, Any] = {}
    message = ""
    try:
        result = run_labstation_command(host, command, args, None, None, None, None, None)
        success = result.get("exit_code", 1) == 0
        message = "Exit code {}".format(result.get("exit_code"))
    except Exception as exc:
        logging.exception("Lab Station command failed for %s", host.get("name"))
        message = "Lab Station command failed"
        result = {"error": message}
    duration_ms = result.get("duration_ms", int((time.time() - start) * 1000))
    status = "completed" if success else "failed"
    summarized = {
        "exitCode": result.get("exit_code"),
        "stdout": (result.get("stdout") or "").strip(),
        "stderr": (result.get("stderr") or "").strip(),
        "args": args,
        "durationMs": duration_ms,
    }
    record_reservation_operation(
        reservation_id,
        lab_id,
        host.get("name", ""),
        action,
        status,
        success,
        response_code=result.get("exit_code"),
        duration_ms=duration_ms,
        payload=summarized,
        message=message,
    )
    if not success:
        notify_critical_failure(reservation_id, lab_id, host.get("name", ""), action, message, summarized)
    return success, {
        "action": action,
        "success": success,
        "status": status,
        "message": message,
        "details": summarized,
    }


def poll_heartbeat(host: Dict[str, Any], include_events: bool = False) -> Dict[str, Any]:
    return _poll_heartbeat_impl(
        host,
        include_events,
        read_remote_file=read_remote_file,
        persist_heartbeat=persist_heartbeat,
        db_engine=DB_ENGINE,
        sync_lab_to_basyx=aas_generator.sync_lab_to_basyx,
        logger=logging,
        default_heartbeat_path=r"C:\LabStation\labstation\data\telemetry\heartbeat.json",
        default_events_path=r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
    )

def database_is_usable(engine: Optional[Engine], statement: str) -> bool:
    return _database_is_usable_impl(
        engine,
        statement,
        sql_text=text,
        logger=logging,
    )


def fernet_key_is_usable() -> bool:
    """Validate the key needed to durably encrypt runtime bearer material."""
    try:
        _load_fernet()
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("OPS_SECRETS_KEY is unavailable or invalid: %s", type(exc).__name__)
        return False


def demo_readiness() -> Dict[str, Any]:
    """Validate the configured demo binding and its physical Station state.

    The worker owns the Guacamole database and Station heartbeat, therefore it
    is the authoritative local check for the connection, principal, exact READ
    grant and physical host. Marketplace eligibility is checked by OpenResty
    against the authority endpoint before a public hand-off.
    """
    raw_lab_id = DEMO_LAB_ID.strip()
    raw_connection_id = DEMO_CONNECTION_ID.strip()
    result: Dict[str, Any] = {
        "status": "disabled",
        "checks": {
            "connection": False,
            "principal": False,
            "permission": False,
            "physical_host": False,
        },
    }
    if not raw_lab_id and not raw_connection_id:
        return result

    if (
        not raw_lab_id.isdigit()
        or not raw_connection_id.isdigit()
        or int(raw_connection_id) <= 0
        or not DEMO_USER
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", DEMO_USER)
    ):
        result["status"] = "misconfigured"
        return result

    lab_id = str(int(raw_lab_id))
    connection_id = int(raw_connection_id)
    result["labId"] = lab_id
    result["connectionId"] = connection_id
    if not GUACAMOLE_DB_ENGINE:
        result["status"] = "unready"
        return result

    try:
        with GUACAMOLE_DB_ENGINE.begin() as conn:
            connection_exists = int(conn.execute(
                text("SELECT COUNT(*) FROM guacamole_connection WHERE connection_id=:connection_id"),
                {"connection_id": connection_id},
            ).scalar_one()) == 1
            principal_exists = int(conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM guacamole_entity e
                    JOIN guacamole_user u ON u.entity_id = e.entity_id
                    WHERE e.name=:username AND e.type='USER'
                    """
                ),
                {"username": DEMO_USER},
            ).scalar_one()) == 1
            permission_rows = conn.execute(
                text(
                    """
                    SELECT cp.connection_id, cp.permission
                    FROM guacamole_connection_permission cp
                    JOIN guacamole_entity e ON e.entity_id = cp.entity_id
                    WHERE e.name=:username AND e.type='USER'
                    ORDER BY cp.connection_id, cp.permission
                    """
                ),
                {"username": DEMO_USER},
            ).mappings().all()
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Demo readiness Guacamole check failed: %s", exc)
        result["status"] = "unready"
        return result

    result["checks"]["connection"] = connection_exists
    result["checks"]["principal"] = principal_exists
    result["checks"]["permission"] = (
        len(permission_rows) == 1
        and int(permission_rows[0]["connection_id"]) == connection_id
        and str(permission_rows[0]["permission"]).upper() == "READ"
    )
    if not connection_exists or not principal_exists or not result["checks"]["permission"]:
        result["status"] = "misconfigured"
        return result

    host = HOSTS.get_by_lab(lab_id)
    if not host:
        result["status"] = "misconfigured"
        return result

    heartbeat = None
    db_engine = DB_ENGINE
    if db_engine:
        try:
            with db_engine.begin() as conn:
                heartbeat = _fetch_latest_heartbeat(conn, host.get("name", ""))
        except Exception as exc:  # pylint: disable=broad-except
            logging.warning("Demo readiness Station heartbeat check failed: %s", exc)

    if not heartbeat:
        result["status"] = "unready"
        return result
    if heartbeat.get("localSession") or heartbeat.get("localMode"):
        result["status"] = "busy"
        return result

    heartbeat_ts = to_utc(heartbeat.get("timestamp"))
    heartbeat_age = (
        (datetime.now(timezone.utc) - heartbeat_ts).total_seconds()
        if heartbeat_ts else None
    )
    result["checks"]["physical_host"] = (
        heartbeat.get("ready") is True
        and heartbeat_age is not None
        and 0 <= heartbeat_age <= DEMO_HEARTBEAT_MAX_AGE_SECONDS
    )
    result["status"] = "ready" if result["checks"]["physical_host"] else "unready"
    return result


@APP.route("/health", methods=["GET"])
def health():
    db_ok = database_is_usable(DB_ENGINE, "SELECT 1")
    fernet_ok = fernet_key_is_usable()
    guacamole_schema_ok = database_is_usable(
        GUACAMOLE_DB_ENGINE,
        """
        SELECT 1
        FROM guacamole_entity e
        LEFT JOIN guacamole_user u ON u.entity_id = e.entity_id
        LEFT JOIN guacamole_connection_permission cp ON cp.entity_id = e.entity_id
        LEFT JOIN guacamole_connection c ON c.connection_id = cp.connection_id
        LIMIT 1
        """,
    )
    failed_revocations = None
    failed_observations = None
    health_db_engine = DB_ENGINE
    if db_ok and health_db_engine:
        try:
            with health_db_engine.connect() as conn:
                failed_revocations = int(conn.execute(text(
                    "SELECT COUNT(*) FROM guacamole_token_revocation_queue WHERE status = 'FAILED'"
                )).scalar_one())
                failed_observations = int(conn.execute(text(
                    "SELECT COUNT(*) FROM gateway_session_observation_outbox WHERE status = 'FAILED'"
                )).scalar_one())
        except Exception as exc:  # pylint: disable=broad-except
            logging.warning("Health durable queue check failed: %s", exc)
    demo = demo_readiness()
    payload, status = _build_health_response_impl(
        hosts_loaded=len(HOSTS.all_hosts()),
        db_ok=db_ok,
        fernet_ok=fernet_ok,
        guacamole_schema_ok=guacamole_schema_ok,
        failed_revocations=failed_revocations,
        failed_observations=failed_observations,
        demo=demo,
    )
    return jsonify(payload), status


@APP.route("/api/wol", methods=["POST"])
def api_wol():
    payload = request.get_json(force=True, silent=True) or {}
    host_name = payload.get("host")
    host = HOSTS.get(host_name) if host_name else None
    mac = payload.get("mac") or (host or {}).get("mac")
    if not mac:
        return jsonify({"error": "mac is required"}), 400

    ping_target = str(payload.get("ping_target") or (host or {}).get("ping_target") or (host or {}).get("address") or "").strip()
    if not ping_target:
        return jsonify({"error": "ping_target or host address is required"}), 400
    if not _is_valid_ping_target(ping_target):
        return jsonify({"error": "ping_target is invalid"}), 400
    attempts = int(payload.get("attempts", 3))
    wait_seconds = float(payload.get("ping_timeout", 10))
    broadcast = payload.get("broadcast")
    port = int(payload.get("port", 9))
    configured_probe_port = (host or {}).get("winrm_port")
    try:
        probe_port = int(configured_probe_port) if configured_probe_port not in (None, "") else None
    except (TypeError, ValueError):
        probe_port = None

    start = time.time()
    try:
        up, used_attempts = wol_and_wait(
            mac, broadcast, port, ping_target, attempts, wait_seconds, probe_port=probe_port
        )
    except Exception as exc:
        return internal_error_response("WOL failed", exc)

    return jsonify({
        "success": up,
        "attempts_used": used_attempts,
        "duration_ms": int((time.time() - start) * 1000),
        "ping_target": ping_target,
    })


@APP.route("/api/winrm", methods=["POST"])
def api_winrm():
    payload = request.get_json(force=True, silent=True) or {}
    host_name = payload.get("host")
    command = payload.get("command")
    args = payload.get("args") or []
    if not host_name or not command:
        return jsonify({"error": "host and command are required"}), 400
    if command not in ALLOWED_WINRM_COMMANDS:
        return jsonify({"error": f"command '{command}' not allowed"}), 400
    host = HOSTS.get(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404
    try:
        result = run_labstation_command(
            host=host,
            command=command,
            args=args,
            user=None,
            password=None,
            transport=payload.get("transport"),
            use_ssl=payload.get("use_ssl"),
            port=payload.get("port"),
        )
        return jsonify(result)
    except Exception as exc:
        if isinstance(exc, WinRMTrustError):
            return jsonify(_winrm_trust_error_payload(host_name, exc.code)), 409
        return internal_error_response("WinRM exec failed", exc)


@APP.route("/api/heartbeat/poll", methods=["POST"])
def api_poll_heartbeat():
    return _handle_heartbeat_poll_impl(
        request.get_json(force=True, silent=True) or {},
        find_host=lambda host_name: HOSTS.get(host_name) if host_name else None,
        poll_heartbeat=poll_heartbeat,
        now=time.time,
        jsonify=jsonify,
        trust_error_type=WinRMTrustError,
        trust_error_payload=_winrm_trust_error_payload,
        missing_credentials_predicate=is_missing_winrm_credentials_error,
        credentials_required_message=WINRM_CREDENTIALS_REQUIRED_MESSAGE,
        internal_error_response=internal_error_response,
    )


def _format_sse_event(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def generate_heartbeat_stream(host: Dict[str, Any], include_events: bool):
    return _generate_heartbeat_stream_impl(
        host,
        include_events,
        poll_heartbeat=poll_heartbeat,
        format_sse_event=_format_sse_event,
        trust_error_type=WinRMTrustError,
        missing_credentials_predicate=is_missing_winrm_credentials_error,
        trust_error_payload=_winrm_trust_error_payload,
        request_id=_request_id,
        logger=logging,
        sanitize_log_value=_sanitize_log_value,
        credentials_required_message=WINRM_CREDENTIALS_REQUIRED_MESSAGE,
        heartbeat_interval_seconds=HEARTBEAT_SSE_INTERVAL_SECONDS,
        sleep=time.sleep,
    )


@APP.route("/api/heartbeat/stream", methods=["GET"])
def api_stream_heartbeat():
    return _handle_heartbeat_stream_route_impl(
        request.args,
        find_host=lambda host_name: HOSTS.get(host_name) if host_name else None,
        generate_stream=generate_heartbeat_stream,
        response_factory=Response,
        stream_with_context=stream_with_context,
        jsonify=jsonify,
    )


def _get_mandatory_field(payload: Dict[str, Any], *keys: str) -> Optional[str]:
    return _get_mandatory_field_impl(payload, *keys)


def _canonical_demo_lab_id(value: Any) -> Optional[str]:
    return _canonical_demo_lab_id_impl(value)


def _demo_context(payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    demo_id = str(payload.get("demoId") or "").strip()
    if not DEMO_OPERATION_ID_RE.fullmatch(demo_id):
        return None, "demoId must be an operational identifier in the form demo:<jti>"

    lab_id = _canonical_demo_lab_id(payload.get("labId"))
    if lab_id is None:
        return None, "labId must be a decimal identifier"
    configured_lab_id = _canonical_demo_lab_id(DEMO_LAB_ID)
    if configured_lab_id is None or configured_lab_id != lab_id:
        return None, "labId does not match the configured demo binding"

    host = HOSTS.get_by_lab(lab_id)
    if not host:
        return None, "no Lab Station host is bound to the demo laboratory"

    if not DB_ENGINE:
        return None, "demo lifecycle persistence is unavailable"

    return {
        "demo_id": demo_id,
        "lab_id": lab_id,
        "host": host,
    }, None


def _demo_operation_completed(demo_id: str, action: str) -> bool:
    if not DB_ENGINE:
        return False
    try:
        with DB_ENGINE.connect() as conn:
            return conn.execute(
                text(
                    "SELECT 1 FROM reservation_operations "
                    "WHERE reservation_id=:reservation_id AND action=:action "
                    "AND success=1 ORDER BY id DESC LIMIT 1"
                ),
                {"reservation_id": demo_id, "action": action},
            ).first() is not None
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Demo lifecycle idempotency check failed: %s", type(exc).__name__)
        return False


def _record_demo_event(
    context: Dict[str, Any],
    event: str,
    success: bool,
    *,
    payload: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> None:
    action = "demo_cleanup" if event == "cleanup" else DEMO_EVENT_ACTIONS.get(event)
    if not action:
        raise ValueError("unsupported demo lifecycle event")
    record_reservation_operation(
        reservation_id=context["demo_id"],
        lab_id=context["lab_id"],
        host_name=context["host"].get("name", ""),
        action=action,
        status="completed" if success else "failed",
        success=success,
        response_code=200 if success else 502,
        payload=payload,
        message=message,
    )


def _demo_host_is_ready(host: Dict[str, Any]) -> bool:
    if not DB_ENGINE:
        return False
    try:
        with DB_ENGINE.connect() as conn:
            heartbeat = _fetch_latest_heartbeat(conn, host.get("name", ""))
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Unable to inspect demo Station heartbeat: %s", type(exc).__name__)
        return False
    if not heartbeat or heartbeat.get("localMode") or heartbeat.get("localSession"):
        return False
    heartbeat_ts = to_utc(heartbeat.get("timestamp"))
    if not heartbeat_ts:
        return False
    age = (datetime.now(timezone.utc) - heartbeat_ts).total_seconds()
    return heartbeat.get("ready") is True and 0 <= age <= DEMO_HEARTBEAT_MAX_AGE_SECONDS


def handle_demo_start(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    context, error = _demo_context(payload)
    if error:
        return {"success": False, "error": error}, 400
    assert context is not None

    demo_id = context["demo_id"]
    if _demo_operation_completed(demo_id, "demo_cleanup"):
        return {"success": False, "error": "demo operation has already been cleaned up"}, 409
    if _demo_operation_completed(demo_id, "demo_start"):
        return {
            "success": True,
            "alreadyStarted": True,
            "operationId": demo_id,
            "labId": context["lab_id"],
            "host": context["host"].get("name"),
            "steps": [],
        }, 200

    requested_wake = parse_bool(payload.get("wake", True), True)
    wake = requested_wake and not _demo_host_is_ready(context["host"])
    guard_grace = payload.get("guardGrace", 30)
    try:
        guard_grace = max(0, min(600, int(guard_grace)))
    except (TypeError, ValueError):
        return {"success": False, "error": "guardGrace must be an integer between 0 and 600"}, 400

    reservation_response, reservation_status = handle_reservation_start({
        "reservationId": demo_id,
        "host": context["host"].get("name"),
        "labId": context["lab_id"],
        "wake": wake,
        "wakeOptions": payload.get("wakeOptions") or {},
        "prepare": True,
        "prepareArgs": [
            f"--guard-grace={guard_grace}",
            "--guard-message=Demo access preparation",
        ],
        "guardGrace": guard_grace,
        "power": payload.get("power", True),
        "actor": "demo-lifecycle",
    })
    started = reservation_response.get("success") is True
    _record_demo_event(
        context,
        "start",
        started,
        payload={"phase": "start", "steps": reservation_response.get("steps", [])},
        message=None if started else "Demo physical preparation failed",
    )
    if not started:
        cleanup_response, cleanup_status = handle_demo_end({
            "demoId": demo_id,
            "labId": context["lab_id"],
            "reason": "failed",
        })
        reservation_response["cleanup"] = cleanup_response
        if cleanup_status >= 500:
            reservation_status = cleanup_status
        return {
            "success": False,
            "operationId": demo_id,
            "labId": context["lab_id"],
            "host": context["host"].get("name"),
            "steps": reservation_response.get("steps", []),
            "cleanup": cleanup_response,
        }, reservation_status

    return {
        "success": True,
        "operationId": demo_id,
        "labId": context["lab_id"],
        "host": context["host"].get("name"),
        "prepared": True,
        "steps": reservation_response.get("steps", []),
    }, 200


def handle_demo_event(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    context, error = _demo_context(payload)
    if error:
        return {"success": False, "error": error}, 400
    assert context is not None
    event = str(payload.get("event") or "").strip().lower()
    if event not in {"connected", "expired", "failed", "disconnected"}:
        return {"success": False, "error": "unsupported demo lifecycle event"}, 400
    if not _demo_operation_completed(context["demo_id"], "demo_start"):
        return {"success": False, "error": "demo physical preparation has not completed"}, 409
    action = DEMO_EVENT_ACTIONS[event]
    if _demo_operation_completed(context["demo_id"], action):
        return {"success": True, "alreadyRecorded": True, "operationId": context["demo_id"]}, 200
    _record_demo_event(context, event, True, payload={"event": event})
    return {"success": True, "operationId": context["demo_id"], "event": event}, 200


def handle_demo_end(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    context, error = _demo_context(payload)
    if error:
        return {"success": False, "error": error}, 400
    assert context is not None
    demo_id = context["demo_id"]
    if _demo_operation_completed(demo_id, "demo_cleanup"):
        return {"success": True, "alreadyReleased": True, "operationId": demo_id}, 200

    reason = str(payload.get("reason") or "disconnected").strip().lower()
    if reason not in {"expired", "failed", "disconnected"}:
        return {"success": False, "error": "reason must be expired, failed or disconnected"}, 400
    reason_action = DEMO_EVENT_ACTIONS[reason]
    if not _demo_operation_completed(demo_id, reason_action):
        _record_demo_event(context, reason, True, payload={"reason": reason})

    reservation_response, reservation_status = handle_reservation_end({
        "reservationId": demo_id,
        "host": context["host"].get("name"),
        "labId": context["lab_id"],
        "release": True,
        "releaseArgs": ["--reboot"],
        "power": payload.get("power", True),
        "actor": "demo-lifecycle",
    })
    released = reservation_response.get("success") is True
    _record_demo_event(
        context,
        "cleanup",
        released,
        payload={"reason": reason, "steps": reservation_response.get("steps", [])},
        message=None if released else "Demo physical cleanup failed",
    )
    return {
        "success": released,
        "operationId": demo_id,
        "labId": context["lab_id"],
        "host": context["host"].get("name"),
        "steps": reservation_response.get("steps", []),
    }, reservation_status if not released else 200


def handle_reservation_start(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    reservation_id = _get_mandatory_field(payload, "reservationId", "reservation_id")
    host_name = _get_mandatory_field(payload, "host", "hostName")
    lab_id = _get_mandatory_field(payload, "labId", "lab_id")

    if not reservation_id or not host_name:
        return {"error": "reservationId and host are required"}, 400

    host = HOSTS.get(host_name)
    if not host:
        return {"error": f"host '{host_name}' not found"}, 404

    wake_enabled = parse_bool(payload.get("wake", True), True)
    prepare_enabled = parse_bool(payload.get("prepare", True), True)
    guard_grace = int(payload.get("guardGrace", 90))
    steps: List[Dict[str, Any]] = []
    success = True
    status_code = 200

    if lab_id:
        power_result = _execute_reservation_power_phase(
            reservation_id,
            lab_id,
            host,
            "pre_start",
            payload,
        )
        steps.extend(power_result.get("steps", []))
        if not power_result.get("success"):
            success = False
            status_code = 502

    if success and wake_enabled:
        ok, step = perform_wake_step(host, reservation_id, lab_id, payload.get("wakeOptions", {}))
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    if success and lab_id:
        power_result = _execute_reservation_power_phase(
            reservation_id,
            lab_id,
            host,
            "post_start",
            payload,
        )
        steps.extend(power_result.get("steps", []))
        if not power_result.get("success"):
            success = False
            status_code = 502

    if success and prepare_enabled:
        prepare_args = normalize_args(payload.get("prepareArgs"), [f"--guard-grace={guard_grace}"])
        ok, step = perform_command_step(host, reservation_id, lab_id, "prepare", "prepare-session", prepare_args)
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    response = {
        "success": success,
        "reservationId": reservation_id,
        "host": host_name,
        "labId": lab_id,
        "steps": steps,
    }
    return response, status_code


def handle_reservation_end(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    reservation_id = _get_mandatory_field(payload, "reservationId", "reservation_id")
    host_name = _get_mandatory_field(payload, "host", "hostName")
    lab_id = _get_mandatory_field(payload, "labId", "lab_id")

    if not reservation_id or not host_name:
        return {"error": "reservationId and host are required"}, 400

    host = HOSTS.get(host_name)
    if not host:
        return {"error": f"host '{host_name}' not found"}, 404

    release_enabled = parse_bool(payload.get("release", True), True)
    power_cfg = payload.get("powerAction")
    steps: List[Dict[str, Any]] = []
    success = True
    status_code = 200

    if lab_id:
        power_result = _execute_reservation_power_phase(
            reservation_id,
            lab_id,
            host,
            "pre_end",
            payload,
        )
        steps.extend(power_result.get("steps", []))
        if not power_result.get("success"):
            success = False
            status_code = 502

    if success and release_enabled:
        release_args = normalize_args(payload.get("releaseArgs"), ["--reboot"])
        ok, step = perform_command_step(host, reservation_id, lab_id, "release", "release-session", release_args)
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    if success and power_cfg:
        mode = power_cfg.get("mode", "shutdown")
        extra_args = normalize_args(power_cfg.get("args"), [])
        args = [mode] + extra_args
        ok, step = perform_command_step(host, reservation_id, lab_id, f"power:{mode}", "power", args)
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    if success and lab_id:
        power_result = _execute_reservation_power_phase(
            reservation_id,
            lab_id,
            host,
            "post_end",
            payload,
        )
        steps.extend(power_result.get("steps", []))
        if not power_result.get("success"):
            success = False
            status_code = 502

    response = {
        "success": success,
        "reservationId": reservation_id,
        "host": host_name,
        "labId": lab_id,
        "steps": steps,
    }
    return response, status_code


@APP.route("/api/reservations/start", methods=["POST"])
def api_reservation_start():
    payload = request.get_json(force=True, silent=True) or {}
    response, status = handle_reservation_start(payload)
    return jsonify(response), status


@APP.route("/api/reservations/end", methods=["POST"])
def api_reservation_end():
    payload = request.get_json(force=True, silent=True) or {}
    response, status = handle_reservation_end(payload)
    return jsonify(response), status


@APP.route("/api/demo/start", methods=["POST"])
def api_demo_start():
    payload = request.get_json(force=True, silent=True) or {}
    response, status = handle_demo_start(payload)
    return jsonify(response), status


@APP.route("/api/demo/event", methods=["POST"])
def api_demo_event():
    payload = request.get_json(force=True, silent=True) or {}
    response, status = handle_demo_event(payload)
    return jsonify(response), status


@APP.route("/api/demo/end", methods=["POST"])
def api_demo_end():
    payload = request.get_json(force=True, silent=True) or {}
    response, status = handle_demo_end(payload)
    return jsonify(response), status


def _to_iso(dt: Any) -> Optional[str]:
    if not dt:
        return None
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt)
        except ValueError:
            return dt
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def _sanitize_limit(value: Optional[str]) -> int:
    if value is None:
        return TIMELINE_DEFAULT_LIMIT
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return TIMELINE_DEFAULT_LIMIT
    return max(1, min(parsed, TIMELINE_MAX_LIMIT))


def _sanitize_offset(value: Optional[str]) -> int:
    if value is None:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _rows_to_operations(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return _rows_to_operations_impl(rows, to_iso=_to_iso)


def build_reservation_timeline(reservation_id: str, limit: int, offset: int) -> Dict[str, Any]:
    if not DB_ENGINE:
        raise RuntimeError("Database not configured")

    with DB_ENGINE.begin() as conn:
        reservation = conn.execute(
            text(
                """
                SELECT transaction_hash, lab_id, status, start_time, end_time,
                       wallet_address, created_at, updated_at
                FROM lab_reservations
                WHERE transaction_hash = :reservation_id
                """
            ),
            {"reservation_id": reservation_id},
        ).mappings().first()

        if not reservation:
            raise LookupError("Reservation not found")

        lab_id = reservation.get("lab_id")
        host = HOSTS.get_by_lab(lab_id)
        host_name = (host or {}).get("name")

        # Get total count for pagination metadata
        total_ops = conn.execute(
            text(
                """
                SELECT COUNT(*) as total
                FROM reservation_operations
                WHERE reservation_id = :reservation_id
                """
            ),
            {"reservation_id": reservation_id},
        ).scalar()
        
        operations = conn.execute(
            text(
                """
                SELECT action, status, success, message, payload,
                       response_code, duration_ms, created_at
                FROM reservation_operations
                WHERE reservation_id = :reservation_id
                ORDER BY created_at ASC, id ASC
                LIMIT :limit_value OFFSET :offset_value
                """
            ),
            {
                "reservation_id": reservation_id,
                "limit_value": limit,
                "offset_value": offset,
            },
        ).mappings().all()
        op_entries = _rows_to_operations([dict(row) for row in operations])

        phase_rows = conn.execute(
            text(
                """
                SELECT action, status, success, message, payload,
                       response_code, duration_ms, created_at
                FROM reservation_operations
                WHERE reservation_id = :reservation_id
                ORDER BY created_at DESC, id DESC
                LIMIT :phase_limit
                """
            ),
            {"reservation_id": reservation_id, "phase_limit": TIMELINE_PHASE_LOOKBACK},
        ).mappings().all()
        phase_entries = _rows_to_operations([dict(row) for row in reversed(phase_rows)])

        latest_heartbeat = None
        if host_name:
            latest_heartbeat = _fetch_latest_heartbeat(conn, host_name)

        phases = _summarize_phases(phase_entries)

        reservation_payload = {
            "reservationId": reservation.get("transaction_hash"),
            "labId": lab_id,
            "status": reservation.get("status"),
            "start": _to_iso(reservation.get("start_time")),
            "end": _to_iso(reservation.get("end_time")),
            "walletAddress": reservation.get("wallet_address"),
            "createdAt": _to_iso(reservation.get("created_at")),
            "updatedAt": _to_iso(reservation.get("updated_at")),
        }

        returned_count = len(op_entries)
        total_ops = total_ops or 0
        next_offset = offset + returned_count
        has_more = total_ops > next_offset
        page = (offset // limit) + 1 if limit else 1

        return {
            "reservation": reservation_payload,
            "host": {
                "name": host_name,
                "labId": lab_id,
                "config": host,
            },
            "operations": op_entries,
            "phases": phases,
            "heartbeat": latest_heartbeat,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "page": page,
                "pageSize": limit,
                "returned": returned_count,
                "total": total_ops,
                "hasMore": has_more,
                "nextOffset": next_offset,
            },
        }


def _fetch_latest_heartbeat(conn: Connection, host_name: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        text(
            """
            SELECT h.timestamp_utc, h.ready, h.local_mode, h.local_session,
                   h.last_power_action_ts, h.last_power_action_mode,
                   h.last_forced_logoff_ts, h.last_forced_logoff_user,
                   h.raw_json
            FROM lab_host_heartbeat h
            JOIN lab_hosts ho ON ho.id = h.host_id
            WHERE ho.name = :host
            ORDER BY h.timestamp_utc DESC
            LIMIT 1
            """
        ),
        {"host": host_name},
    ).mappings().first()

    if not row:
        return None

    raw = row.get("raw_json")
    parsed_raw = None
    if isinstance(raw, str):
        try:
            parsed_raw = json.loads(raw)
        except json.JSONDecodeError:
            parsed_raw = None

    return {
        "timestamp": _to_iso(row.get("timestamp_utc")),
        "ready": bool(row.get("ready")),
        "localMode": bool(row.get("local_mode")),
        "localSession": bool(row.get("local_session")),
        "lastPower": {
            "timestamp": _to_iso(row.get("last_power_action_ts")),
            "mode": row.get("last_power_action_mode"),
        },
        "lastForcedLogoff": {
            "timestamp": _to_iso(row.get("last_forced_logoff_ts")),
            "user": row.get("last_forced_logoff_user"),
        },
        "raw": parsed_raw,
    }


def _summarize_phases(operations: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    def picker(prefixes: List[str]) -> Optional[Mapping[str, Any]]:
        for entry in reversed(operations):
            action = entry.get("action") or ""
            if any(action.startswith(prefix) for prefix in prefixes):
                return entry
        return None

    return {
        "wake": picker(["wake", "scheduler:start"]),
        "prepare": picker(["prepare"]),
        "release": picker(["release"]),
        "power": picker(["power:"]),
        "schedulerEnd": picker(["scheduler:end"]),
    }


@APP.route("/api/reservations/timeline", methods=["GET"])
def api_reservation_timeline():
    return _handle_reservation_timeline_impl(
        request.args,
        db_engine=DB_ENGINE,
        sanitize_limit=_sanitize_limit,
        sanitize_offset=_sanitize_offset,
        build_timeline=build_reservation_timeline,
        jsonify=jsonify,
        internal_error_response=internal_error_response,
    )


def normalize_match_key(value: Optional[Any]) -> str:
    return str(value or "").strip().lower()


def tcp_port_open(host: str, port: int, timeout: Optional[float] = None) -> bool:
    try:
        with socket.create_connection((host, port), timeout or DISCOVERY_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def response_looks_like_labstation(response: requests.Response) -> Tuple[bool, Optional[str]]:
    return _response_looks_like_labstation_impl(response)

def normalize_mac(value: Any) -> str:
    return _normalize_mac_impl(value, mac_pattern=MAC_RE)


def parse_boolish(value: Any) -> bool:
    return _parse_boolish_impl(value)


def extract_nic_candidates_from_heartbeat(heartbeat: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _extract_nic_candidates_from_heartbeat_impl(
        heartbeat,
        normalize_mac_fn=normalize_mac,
        parse_boolish_fn=parse_boolish,
    )


def choose_wol_mac(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return _choose_wol_mac_impl(candidates)


def suggest_mac_from_heartbeat(heartbeat: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _suggest_mac_from_heartbeat_impl(
        heartbeat,
        normalize_mac_fn=normalize_mac,
        parse_boolish_fn=parse_boolish,
    )


def probe_labstation_http(host: str) -> Dict[str, Any]:
    return _probe_labstation_http_impl(
        host,
        ports=DISCOVERY_LABSTATION_PORTS,
        paths=DISCOVERY_LABSTATION_PATHS,
        timeout=DISCOVERY_TIMEOUT_SECONDS,
        http_get=requests.get,
        request_exception_type=requests.RequestException,
        response_classifier=response_looks_like_labstation,
        suggest_mac=suggest_mac_from_heartbeat,
    )

def query_labstation_task_heartbeat_path(host: Dict[str, Any]) -> Optional[str]:
    return _query_labstation_task_heartbeat_path_impl(
        host,
        run_remote_powershell=run_remote_powershell,
        parse_json=json.loads,
        logger=logging,
    )


def build_heartbeat_path_candidates(host: Dict[str, Any]) -> List[str]:
    return _build_heartbeat_path_candidates_impl(
        host,
        query_task_path=query_labstation_task_heartbeat_path,
        configured_paths=DISCOVERY_HEARTBEAT_PATHS,
    )


def discover_heartbeat_hint(hostname: str) -> Dict[str, Any]:
    return _discover_heartbeat_hint_impl(
        hostname,
        credentials_configured=winrm_credentials_configured,
        path_candidates=build_heartbeat_path_candidates,
        read_remote_file=read_remote_file,
        parse_json=json.loads,
        suggest_mac=suggest_mac_from_heartbeat,
        winrm_port=WINRM_PORT,
        logger=logging,
    )


def guacamole_name_candidates(connection: Dict[str, Any]) -> List[str]:
    return _guacamole_name_candidates_impl(
        connection,
        load_connections=load_guacamole_connections,
        normalize_key=normalize_match_key,
    )


def resolve_guacamole_connection(connection_id: Any) -> Optional[Dict[str, Any]]:
    return _resolve_guacamole_connection_impl(
        connection_id,
        load_connections=load_guacamole_connections,
    )


def discover_labstation_candidate(connection: Dict[str, Any]) -> Dict[str, Any]:
    return _discover_labstation_candidate_impl(
        connection,
        normalize_host=normalize_match_key,
        resolve_dns=socket.getaddrinfo,
        tcp_probe=tcp_port_open,
        http_probe=probe_labstation_http,
        heartbeat_hint=discover_heartbeat_hint,
        name_candidates=guacamole_name_candidates,
        winrm_port=WINRM_PORT,
        discovery_timeout=DISCOVERY_TIMEOUT_SECONDS,
        heartbeat_paths=DISCOVERY_HEARTBEAT_PATHS,
        draft_winrm_port=5986,
        events_path=r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
    )


def sanitize_host_name(value: Any, fallback: Optional[Any]) -> Tuple[Optional[str], Optional[str]]:
    return _sanitize_host_name_impl(value, fallback, name_pattern=HOST_NAME_RE)

def normalize_labs(value: Any) -> List[str]:
    return _normalize_labs_impl(value)

def validate_labs_against_candidates(labs: List[str], candidates: Any) -> Optional[str]:
    return _validate_labs_against_candidates_impl(labs, candidates)

def load_dynamic_config() -> Dict[str, Any]:
    return _load_dynamic_config_impl(
        DYNAMIC_CONFIG_PATH,
        read_config=read_hosts_config,
    )


def write_dynamic_config(config: Dict[str, Any]) -> None:
    return _write_dynamic_config_impl(
        config,
        DYNAMIC_CONFIG_PATH,
        path_dirname=os.path.dirname,
        make_dirs=os.makedirs,
        open_file=open,
        dump_json=json.dump,
        replace_file=os.replace,
    )


def upsert_dynamic_host(host_config: Dict[str, Any]) -> None:
    return _upsert_dynamic_host_impl(
        host_config,
        load_config=load_dynamic_config,
        write_config=write_dynamic_config,
    )


def build_provisioned_host(payload: Dict[str, Any], connection: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    return _build_provisioned_host_impl(
        payload,
        connection,
        sanitize_host_name_fn=sanitize_host_name,
        normalize_labs_fn=normalize_labs,
        validate_labs_fn=validate_labs_against_candidates,
        normalize_mac_fn=normalize_mac,
        normalize_trust_ref_fn=normalize_winrm_trust_ref,
        default_heartbeat_path=r"C:\LabStation\labstation\data\telemetry\heartbeat.json",
        default_events_path=r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
    )

def update_dynamic_host(host_name: str, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    return _update_dynamic_host_impl(
        host_name,
        payload,
        load_config=load_dynamic_config,
        write_config=write_dynamic_config,
        normalize_key=normalize_match_key,
        sanitize_name=sanitize_host_name,
        normalize_mac=normalize_mac,
        host_get=HOSTS.get,
    )


def safe_host_inventory_entry(host: Dict[str, Any], *, editable: bool = False) -> Dict[str, Any]:
    return _safe_host_inventory_entry_impl(
        host,
        editable=editable,
        credential_ref_for_host=credential_ref_for_host,
        inspect_winrm_trust=inspect_winrm_trust,
        winrm_credentials_configured=winrm_credentials_configured,
        default_heartbeat_path=r"C:\LabStation\labstation\data\telemetry\heartbeat.json",
    )

def load_guacamole_connections() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    return _load_guacamole_connections_impl(
        GUACAMOLE_DB_ENGINE,
        sql_text=text,
        logger=logging,
    )


def require_guacamole_provisioner_auth():
    expected = str(GUACAMOLE_PROVISIONER_TOKEN or "").strip()
    if not expected:
        return None
    provided = request.headers.get(GUACAMOLE_PROVISIONER_TOKEN_HEADER)
    if not provided and GUACAMOLE_PROVISIONER_TOKEN_HEADER.lower() != "x-lab-manager-token":
        provided = request.headers.get("X-Lab-Manager-Token")
    if provided != expected:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return None


def parse_guacamole_selector(selector: Any) -> int:
    return _parse_guacamole_selector_impl(
        selector,
        selector_pattern=GUAC_SELECTOR_RE,
    )


def safe_connection_response(connection: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_connection_response_impl(connection)


def provision_guacamole_temporary_user(
    selector: str,
    session_id: str,
    valid_until_epoch: Optional[Any],
    activate: bool = True,
) -> Dict[str, Any]:
    if not GUACAMOLE_DB_ENGINE:
        raise RuntimeError("Guacamole database not configured")
    connection_id = parse_guacamole_selector(selector)
    if not session_id or not re.match(r"^[A-Za-z0-9_.-]{1,128}$", str(session_id)):
        raise ValueError("sessionId is required and must be a safe identifier")
    username = f"dlabs-res-{session_id}"
    valid_until_date = None
    if valid_until_epoch not in (None, ""):
        valid_until_date = datetime.fromtimestamp(int(valid_until_epoch), tz=timezone.utc).date().isoformat()

    connection = resolve_guacamole_connection(connection_id)
    if not connection:
        raise ValueError(f"Guacamole connection {connection_id} not found")

    with GUACAMOLE_DB_ENGINE.begin() as conn:
        if conn.dialect.name == "mysql":
            conn.execute(
                text(
                    """
                    INSERT INTO guacamole_entity (name, type)
                    VALUES (:username, 'USER')
                    ON DUPLICATE KEY UPDATE name = VALUES(name)
                    """
                ),
                {"username": username},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO guacamole_entity (name, type)
                    VALUES (:username, 'USER')
                    """
                ),
                {"username": username},
            )

        entity_id = conn.execute(
            text("SELECT entity_id FROM guacamole_entity WHERE name = :username AND type = 'USER'"),
            {"username": username},
        ).scalar()
        if entity_id is None:
            raise RuntimeError("Unable to resolve temporary Guacamole entity")

        if conn.dialect.name == "mysql":
            conn.execute(
                text(
                    """
                    INSERT INTO guacamole_user (entity_id, password_hash, password_date, disabled, expired, valid_until)
                    VALUES (:entity_id, UNHEX(SHA2(UUID(), 256)), UTC_TIMESTAMP(), :disabled, FALSE, :valid_until)
                    ON DUPLICATE KEY UPDATE disabled = VALUES(disabled), expired = FALSE, valid_until = VALUES(valid_until)
                    """
                ),
                {"entity_id": entity_id, "disabled": not activate, "valid_until": valid_until_date},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT OR REPLACE INTO guacamole_user (entity_id, valid_until, disabled)
                    VALUES (:entity_id, :valid_until, :disabled)
                    """
                ),
                {"entity_id": entity_id, "disabled": not activate, "valid_until": valid_until_date},
            )

        if activate:
            if conn.dialect.name == "mysql":
                conn.execute(
                    text(
                        """
                        INSERT INTO guacamole_connection_permission (entity_id, connection_id, permission)
                        VALUES (:entity_id, :connection_id, 'READ')
                        ON DUPLICATE KEY UPDATE permission = VALUES(permission)
                        """
                    ),
                    {"entity_id": entity_id, "connection_id": connection_id},
                )
            else:
                conn.execute(
                    text(
                        """
                        INSERT OR REPLACE INTO guacamole_connection_permission (entity_id, connection_id, permission)
                        VALUES (:entity_id, :connection_id, 'READ')
                        """
                    ),
                    {"entity_id": entity_id, "connection_id": connection_id},
                )
        else:
            conn.execute(
                text("DELETE FROM guacamole_connection_permission WHERE entity_id = :entity_id"),
                {"entity_id": entity_id},
            )

    logging.info("Provisioned temporary Guacamole user")
    return {
        "success": True,
        "sessionId": session_id,
        "username": username,
        "connection": safe_connection_response(connection),
    }


def delete_guacamole_temporary_user(session_id: str) -> bool:
    if not GUACAMOLE_DB_ENGINE:
        raise RuntimeError("Guacamole database not configured")
    if not session_id or not re.match(r"^[A-Za-z0-9_.-]{1,128}$", str(session_id)):
        raise ValueError("sessionId is required and must be a safe identifier")
    username = f"dlabs-res-{session_id}"
    with GUACAMOLE_DB_ENGINE.begin() as conn:
        entity_id = conn.execute(
            text("SELECT entity_id FROM guacamole_entity WHERE name = :username AND type = 'USER'"),
            {"username": username},
        ).scalar()
        if entity_id is None:
            return False
        conn.execute(text("DELETE FROM guacamole_connection_permission WHERE entity_id = :entity_id"), {"entity_id": entity_id})
        conn.execute(text("DELETE FROM guacamole_user WHERE entity_id = :entity_id"), {"entity_id": entity_id})
        conn.execute(text("DELETE FROM guacamole_entity WHERE entity_id = :entity_id"), {"entity_id": entity_id})
    logging.info(
        "Deleted temporary Guacamole user %s",
        str(username).replace("\r", "\\r").replace("\n", "\\n"),
    )
    return True


def cleanup_expired_guacamole_temp_users() -> int:
    if not GUACAMOLE_DB_ENGINE:
        logging.debug("Skipping Guacamole temp user cleanup: database not configured")
        return 0
    try:
        with GUACAMOLE_DB_ENGINE.begin() as conn:
            if conn.dialect.name == "mysql":
                result = conn.execute(
                    text(
                        """
                        DELETE e FROM guacamole_entity e
                        JOIN guacamole_user u ON u.entity_id = e.entity_id
                        WHERE e.type = 'USER'
                          AND e.name LIKE 'dlabs-res-%'
                          AND u.valid_until IS NOT NULL
                          AND u.valid_until < UTC_DATE()
                        """
                    )
                )
            else:
                result = conn.execute(
                    text(
                        """
                        DELETE FROM guacamole_entity
                        WHERE entity_id IN (
                            SELECT e.entity_id
                            FROM guacamole_entity e
                            JOIN guacamole_user u ON u.entity_id = e.entity_id
                            WHERE e.type = 'USER'
                              AND e.name LIKE 'dlabs-res-%'
                              AND u.valid_until IS NOT NULL
                              AND u.valid_until < CURRENT_DATE
                        )
                        """
                    )
                )
        deleted = result.rowcount if result.rowcount is not None else 0
        if deleted:
            logging.info("Cleaned up %s expired Guacamole temporary users", deleted)
        return deleted
    except Exception as exc:
        logging.warning("Guacamole temp user cleanup failed: %s", exc)
        return 0


def build_host_inventory() -> Dict[str, Any]:
    with HOSTS_LOCK:
        hosts = HOSTS.all_hosts()
    dynamic_config = load_dynamic_config()
    guacamole_connections, guacamole_error = load_guacamole_connections()
    return _build_host_inventory_impl(
        hosts,
        dynamic_config,
        guacamole_connections,
        guacamole_error,
        normalize_key=normalize_match_key,
        safe_entry=safe_host_inventory_entry,
    )


@APP.route("/api/hosts", methods=["GET"])
def api_hosts_inventory():
    return _handle_hosts_inventory_impl(
        build_inventory=build_host_inventory,
        jsonify=jsonify,
    )


@APP.route("/internal/guacamole/connections", methods=["GET"])
def api_internal_guacamole_connections():
    return _handle_guacamole_connections_impl(
        authorize=require_guacamole_provisioner_auth,
        load_connections=load_guacamole_connections,
        safe_connection_response=safe_connection_response,
        jsonify=jsonify,
    )


@APP.route("/internal/guacamole/provision", methods=["POST"])
def api_internal_guacamole_provision():
    return _handle_guacamole_provision_impl(
        request.get_json(silent=True) or {},
        authorize=require_guacamole_provisioner_auth,
        provision_temporary_user=provision_guacamole_temporary_user,
        jsonify=jsonify,
        internal_error_response=internal_error_response,
    )


@APP.route("/internal/guacamole/provision/<session_id>", methods=["DELETE"])
def api_internal_guacamole_delete(session_id: str):
    return _handle_guacamole_cleanup_impl(
        session_id,
        authorize=require_guacamole_provisioner_auth,
        delete_temporary_user=delete_guacamole_temporary_user,
        jsonify=jsonify,
        internal_error_response=internal_error_response,
    )


@APP.route("/api/hosts/discover", methods=["POST"])
def api_hosts_discover():
    return _handle_hosts_discover_impl(
        request.get_json(force=True, silent=True) or {},
        resolve_connection=resolve_guacamole_connection,
        discover_candidate=discover_labstation_candidate,
        jsonify=jsonify,
    )


@APP.route("/api/hosts/provision", methods=["POST"])
def api_hosts_provision():
    payload = request.get_json(force=True, silent=True) or {}
    connection_id = payload.get("connectionId") or payload.get("connection_id")
    if connection_id in (None, ""):
        return jsonify({"error": "connectionId is required"}), 400

    connection = resolve_guacamole_connection(connection_id)
    if not connection:
        return jsonify({"error": f"Guacamole connection {connection_id} not found"}), 404

    discovery = discover_labstation_candidate(connection)
    if discovery.get("status") not in ENOUGH_DISCOVERY_SIGNALS:
        return jsonify({
            "error": "insufficient discovery signal for ops host provisioning",
            "discovery": discovery,
        }), 409

    provision_payload = dict(payload)
    if not str(provision_payload.get("mac") or "").strip():
        ops_host_draft = discovery.get("opsHostDraft")
        suggested_mac = ops_host_draft.get("mac") if isinstance(ops_host_draft, dict) else None
        if suggested_mac:
            provision_payload["mac"] = suggested_mac

    host_config, error = build_provisioned_host(provision_payload, connection)
    if error:
        return jsonify({"error": error}), 400
    if host_config is None:
        return jsonify({"error": "host configuration could not be built"}), 400

    existing = HOSTS.get(host_config["name"])
    if existing:
        return jsonify({"error": f"host {host_config['name']} already exists"}), 409

    try:
        upsert_dynamic_host(host_config)
        count, reload_error = reload_hosts()
    except PermissionError:
        return jsonify({
            "error": "Ops host catalog is not writable; check the ops-data mount permissions",
            "code": "OPS_DYNAMIC_CONFIG_NOT_WRITABLE",
        }), 503
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
            return jsonify({
                "error": "Ops host catalog is not writable; check the ops-data mount permissions",
                "code": "OPS_DYNAMIC_CONFIG_NOT_WRITABLE",
            }), 503
        return internal_error_response("Failed to provision ops host", exc)
    except Exception as exc:
        return internal_error_response("Failed to provision ops host", exc)

    if reload_error:
        return jsonify({"error": "Hosts configuration reload failed"}), 500

    return jsonify({
        "provisioned": True,
        "hosts": count,
        "host": safe_host_inventory_entry(host_config, editable=True),
        "discoveryStatus": discovery.get("status"),
    })


@APP.route("/api/hosts/<host_name>", methods=["PATCH"])
def api_hosts_update(host_name: str):
    payload = request.get_json(force=True, silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "host update payload must be an object"}), 400

    try:
        host_config, error = update_dynamic_host(host_name, payload)
        if error:
            status = 409 if "static catalog" in error or "already exists" in error else 400
            return jsonify({"error": error}), status
        if host_config is None:
            return jsonify({"error": "host configuration could not be updated"}), 400
        count, reload_error = reload_hosts()
    except PermissionError:
        return jsonify({
            "error": "Ops host catalog is not writable; check the ops-data mount permissions",
            "code": "OPS_DYNAMIC_CONFIG_NOT_WRITABLE",
        }), 503
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
            return jsonify({
                "error": "Ops host catalog is not writable; check the ops-data mount permissions",
                "code": "OPS_DYNAMIC_CONFIG_NOT_WRITABLE",
            }), 503
        return internal_error_response("Failed to update ops host", exc)
    except Exception as exc:
        return internal_error_response("Failed to update ops host", exc)

    if reload_error:
        return jsonify({"error": "Hosts configuration reload failed"}), 500

    return jsonify({
        "updated": True,
        "hosts": count,
        "host": safe_host_inventory_entry(host_config, editable=True),
    })


def _winrm_trust_http_status(code: str) -> int:
    if code == "WINRM_TRUST_STORAGE_UNAVAILABLE":
        return 503
    if code in {
        "WINRM_CERTIFICATE_HOST_MISMATCH",
        "WINRM_CERTIFICATE_EXPIRED",
        "WINRM_CERTIFICATE_NOT_YET_VALID",
        "WINRM_FINGERPRINT_MISMATCH",
        "WINRM_TRUST_REF_MISMATCH",
    }:
        return 422
    return 400


def _winrm_trust_host_or_404(host_name: str):
    host = HOSTS.get(host_name)
    if not host:
        return None, (jsonify({"error": f"host '{host_name}' not found in config"}), 404)
    return host, None


@APP.route("/api/hosts/<host_name>/winrm-trust/preview", methods=["POST"])
def api_preview_winrm_trust(host_name: str):
    host, error_response = _winrm_trust_host_or_404(host_name)
    if error_response:
        return error_response
    if host is None:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404
    try:
        raw = _read_winrm_certificate_upload()
        certificate = _parse_winrm_certificate_bytes(raw)
        input_format = "PEM" if b"-----BEGIN CERTIFICATE-----" in raw[:256] else "DER"
        preview = _winrm_certificate_response_metadata(certificate, host, input_format)
        try:
            _validate_winrm_certificate(certificate, host)
        except WinRMTrustError as exc:
            payload = _winrm_trust_error_payload(host_name, exc.code)
            payload["preview"] = preview
            return jsonify(payload), _winrm_trust_http_status(exc.code)
        preview["valid"] = True
        return jsonify({
            "requestId": _request_id(),
            "host": host.get("name"),
            "address": host.get("address"),
            "preview": preview,
        })
    except WinRMTrustError as exc:
        return jsonify(_winrm_trust_error_payload(host_name, exc.code)), _winrm_trust_http_status(exc.code)
    except Exception as exc:
        return internal_error_response("WinRM trust preview failed", exc)


@APP.route("/api/hosts/<host_name>/winrm-trust", methods=["GET"])
def api_get_winrm_trust(host_name: str):
    return _handle_winrm_trust_get_impl(
        host_name,
        find_host=HOSTS.get,
        inspect_trust=inspect_winrm_trust,
        request_id=_request_id,
        trust_error_type=WinRMTrustError,
        trust_error_payload=_winrm_trust_error_payload,
        trust_http_status=_winrm_trust_http_status,
        jsonify=jsonify,
        internal_error_response=internal_error_response,
    )


@APP.route("/api/hosts/<host_name>/winrm-trust", methods=["PUT"])
def api_save_winrm_trust(host_name: str):
    host, error_response = _winrm_trust_host_or_404(host_name)
    if error_response:
        return error_response
    if host is None:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404
    try:
        submitted_fingerprint = (
            _winrm_trust_request_value("fingerprintSha256")
            or str(request.headers.get("X-WinRM-Fingerprint-SHA256") or "").strip()
        )
        submitted_fingerprint = re.sub(r"[\s:]", "", submitted_fingerprint).upper()
        if not submitted_fingerprint:
            raise WinRMTrustError(
                "WINRM_FINGERPRINT_CONFIRMATION_REQUIRED",
                WINRM_FINGERPRINT_CONFIRMATION_REQUIRED_MESSAGE,
            )
        if not re.fullmatch(r"[0-9A-F]{64}", submitted_fingerprint):
            raise WinRMTrustError("WINRM_FINGERPRINT_MISMATCH", WINRM_FINGERPRINT_MISMATCH_MESSAGE)

        supplied_trust_ref = (
            _winrm_trust_request_value("trustRef")
            or str(request.headers.get("X-WinRM-Trust-Ref") or "").strip()
        )
        if supplied_trust_ref:
            try:
                if normalize_winrm_trust_ref(supplied_trust_ref) != winrm_trust_ref_for_host(host):
                    raise WinRMTrustError("WINRM_TRUST_REF_MISMATCH", WINRM_TRUST_REF_MISMATCH_MESSAGE)
            except ValueError as exc:
                raise WinRMTrustError("WINRM_TRUST_REF_MISMATCH", WINRM_TRUST_REF_MISMATCH_MESSAGE) from exc

        raw = _read_winrm_certificate_upload()
        certificate = _parse_winrm_certificate_bytes(raw)
        metadata = _validate_winrm_certificate(certificate, host)
        if metadata["fingerprintSha256"] != submitted_fingerprint:
            raise WinRMTrustError("WINRM_FINGERPRINT_MISMATCH", WINRM_FINGERPRINT_MISMATCH_MESSAGE)

        trust = _store_winrm_trust_certificate(host, certificate)
        logging.info(
            "WinRM trust saved host=%s fingerprintSha256=%s",
            _sanitize_log_value(host_name),
            _sanitize_log_value(metadata["fingerprintSha256"]),
        )
        return jsonify({
            "requestId": _request_id(),
            "saved": True,
            "host": host.get("name"),
            "address": host.get("address"),
            "trust": trust,
        })
    except WinRMTrustError as exc:
        return jsonify(_winrm_trust_error_payload(host_name, exc.code)), _winrm_trust_http_status(exc.code)
    except OSError as exc:
        logging.warning("Unable to save WinRM trust for %s: %s", _sanitize_log_value(host_name), type(exc).__name__)
        return jsonify(_winrm_trust_error_payload(
            host_name,
            "WINRM_TRUST_STORAGE_UNAVAILABLE",
        )), 503
    except Exception as exc:
        return internal_error_response("WinRM trust save failed", exc)


@APP.route("/api/hosts/<host_name>/winrm-trust", methods=["DELETE"])
def api_delete_winrm_trust(host_name: str):
    host, error_response = _winrm_trust_host_or_404(host_name)
    if error_response:
        return error_response
    if host is None:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404
    try:
        _delete_winrm_trust_certificate(host)
        logging.info("WinRM trust removed host=%s", _sanitize_log_value(host_name))
        return jsonify({
            "requestId": _request_id(),
            "deleted": True,
            "host": host.get("name"),
            "address": host.get("address"),
            "trust": inspect_winrm_trust(host),
        })
    except WinRMTrustError as exc:
        return jsonify(_winrm_trust_error_payload(host_name, exc.code)), _winrm_trust_http_status(exc.code)
    except Exception as exc:
        return internal_error_response("WinRM trust delete failed", exc)


@APP.route("/api/hosts/winrm-credentials", methods=["POST"])
def api_save_winrm_credentials():
    payload = request.get_json(force=True, silent=True) or {}
    credential_ref = payload.get("credentialRef") or payload.get("credential_ref")
    user = payload.get("user") or payload.get("username")
    password = payload.get("password")
    try:
        save_winrm_credentials(str(credential_ref or ""), str(user or ""), str(password or ""))
        count, reload_error = reload_hosts()
    except ValueError as exc:
        return jsonify({"error": "Invalid WinRM credentials request"}), 400
    except Exception as exc:  # pylint: disable=broad-except
        return internal_error_response("Failed to save WinRM credentials", exc)
    if reload_error:
        return jsonify({"error": "Hosts configuration reload failed"}), 500
    return jsonify({
        "saved": True,
        "credentialRef": normalize_credential_ref(credential_ref),
        "hosts": count,
    })


@APP.route("/api/hosts/reload", methods=["POST"])
def api_hosts_reload():
    return _handle_hosts_reload_impl(
        reload_hosts=reload_hosts,
        jsonify=jsonify,
    )


@APP.route("/api/aas-sync", methods=["POST"])
def api_aas_sync():
    """
    Sync AAS shells for all labs mapped to the given host.

    This is a convenience wrapper over /aas-admin/lab/<lab_id>/sync for the
    lab-manager UI, which knows hosts by name but not individual lab IDs.
    Protected at OpenResty via LAB_MANAGER_TOKEN (same as /ops/api/*).

    Request body: { "host": "<host-name>" }
    Response: { "host": "...", "labs": [{ "labId": "1", "synced": true, ... }] }
    """
    return _handle_aas_sync_impl(
        request.get_json(force=True, silent=True) or {},
        find_host=HOSTS.get,
        sync_lab=aas_generator.sync_lab_to_basyx,
        log_failure=logging.exception,
        jsonify=jsonify,
    )


@APP.route("/api/hosts/local-mode", methods=["POST"])
def api_hosts_local_mode():
    payload = request.get_json(force=True, silent=True) or {}
    host_name = payload.get("host")
    if host_name is None:
        return jsonify({"error": "host is required"}), 400
    enabled = payload.get("enabled")
    if enabled is None:
        return jsonify({"error": "enabled is required"}), 400
    enabled = parse_bool(enabled, False)

    host = HOSTS.get(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found"}), 404

    flag_path = get_local_mode_flag_path(host)
    try:
        if enabled:
            write_remote_file(host, flag_path, "1", None, None, None, None, None)
        else:
            remove_remote_file(host, flag_path, None, None, None, None, None)
    except Exception as exc:
        return internal_error_response(f"Local mode toggle failed for {host_name}", exc)

    return jsonify({"host": host_name, "localModeEnabled": enabled}), 200


@APP.route("/api/operations/recent", methods=["GET"])
def api_operations_recent():
    return _handle_operations_recent_impl(
        request.args,
        db_engine=DB_ENGINE,
        find_host=lambda host_name: HOSTS.get(host_name) if host_name else None,
        sanitize_limit=_sanitize_limit,
        sanitize_offset=_sanitize_offset,
        sql_text=text,
        rows_to_operations=_rows_to_operations,
        jsonify=jsonify,
        internal_error_response=internal_error_response,
    )


@APP.route("/aas-admin/lab/<lab_id>/sync", methods=["POST"])
def api_aas_sync_lab(lab_id: str):
    """
    Sync (create or update) the AAS shell and submodels for a physical lab resource.

    This endpoint is protected at the OpenResty layer via lab_manager_admin_access.lua
    and is only available on Full Gateway instances (--profile aas).

    Optional JSON body:
      { "includeHeartbeat": true }  — polls fresh heartbeat before syncing (default: false)

    The host is resolved from the lab_id via the HOSTS registry.
    If the lab_id is not mapped, returns 404.
    """
    host = HOSTS.get_by_lab(lab_id)
    if not host:
        return jsonify({"error": f"No host mapping found for labId '{lab_id}'"}), 404

    payload = request.get_json(silent=True) or {}
    include_heartbeat = parse_bool(payload.get("includeHeartbeat", False), False)

    heartbeat_data: Optional[Dict[str, Any]] = None
    if include_heartbeat:
        try:
            poll_result = poll_heartbeat(host, include_events=False)
            heartbeat_data = poll_result.get("heartbeat")
        except Exception as exc:
            logging.warning(
                "AAS sync: could not poll heartbeat for lab %s: %s",
                str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
                type(exc).__name__,
            )
    elif DB_ENGINE:
        # Use latest persisted heartbeat from DB if available
        try:
            with DB_ENGINE.begin() as conn:
                heartbeat_data_row = _fetch_latest_heartbeat(conn, host.get("name", ""))
                if heartbeat_data_row and heartbeat_data_row.get("raw"):
                    heartbeat_data = heartbeat_data_row["raw"]
        except Exception as exc:
            logging.warning(
                "AAS sync: could not load heartbeat from DB for lab %s: %s",
                str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
                type(exc).__name__,
            )

    result = aas_generator.sync_lab_to_basyx(str(lab_id), host, heartbeat_data)

    if result.get("disabled"):
        return jsonify(result), 200

    if result.get("error"):
        return jsonify({"detail": result["error"], **result}), 502

    return jsonify(result), 200


def poll_all_hosts():
    return _poll_all_hosts_impl(HOSTS, poll_heartbeat, logging)


class ReservationOrchestrator:
    def __init__(self, engine: Optional[Engine], registry: HostRegistry):
        self.engine = engine
        self.registry = registry
        self.enabled = parse_bool(os.getenv("OPS_RESERVATION_AUTOMATION", False), False)
        self.scan_interval = int(os.getenv("OPS_RESERVATION_SCAN_INTERVAL", "30"))
        self.start_lead = int(os.getenv("OPS_RESERVATION_START_LEAD", "120"))
        self.end_delay = int(os.getenv("OPS_RESERVATION_END_DELAY", "60"))
        self.lookback = int(os.getenv("OPS_RESERVATION_LOOKBACK", "21600"))  # 6 hours
        self.retry_cooldown = int(os.getenv("OPS_RESERVATION_RETRY_COOLDOWN", "60"))
        self.projection_url = os.getenv("RESERVATION_PROJECTION_URL", "").strip().rstrip("/")
        self.projection_gateway_id = os.getenv("RESERVATION_PROJECTION_GATEWAY_ID", "").strip().lower()
        self.projection_token = _env_or_secret_file("RESERVATION_PROJECTION_TOKEN")
        if self.projection_url and not (self.projection_gateway_id and self.projection_token):
            logging.error(
                "Reservation projection is configured but gateway ID or token is missing; "
                "remote reservation automation will remain unavailable"
            )

    def register(self, scheduler: BackgroundScheduler) -> int:
        if not self.enabled:
            logging.info("Reservation orchestrator disabled (OPS_RESERVATION_AUTOMATION=false)")
            return 0
        if not self.engine:
            logging.warning("Reservation orchestrator disabled: ops database DSN is not configured")
            return 0
        scheduler.add_job(
            self.scan_once,
            "interval",
            seconds=self.scan_interval,
            next_run_time=datetime.now(timezone.utc),
            id="reservation-orchestrator",
            replace_existing=True,
        )
        logging.info(
            "Reservation orchestrator enabled (scan=%ss, lead=%ss, end_delay=%ss)",
            self.scan_interval,
            self.start_lead,
            self.end_delay,
        )
        return 1

    def scan_once(self):
        if not self.enabled or not self.engine:
            return
        now = datetime.now(timezone.utc)
        try:
            with self.engine.begin() as conn:
                if self.projection_url:
                    remote_rows = self._fetch_remote_candidates(now)
                    start_rows, end_rows = self._select_remote_candidates(conn, remote_rows, now)
                else:
                    start_rows = self._fetch_start_candidates(conn, now)
                    end_rows = self._fetch_end_candidates(conn, now)
        except Exception as exc:
            logging.error("Reservation orchestrator query failed: %s", exc)
            return

        for row in start_rows:
            self._dispatch_start(dict(row))
        for row in end_rows:
            self._dispatch_end(dict(row))

    def _fetch_remote_candidates(self, now: datetime) -> List[Dict[str, Any]]:
        if not self.projection_gateway_id or not self.projection_token:
            raise RuntimeError("Reservation projection credentials are not configured")
        window_lower = now - timedelta(seconds=self.lookback)
        window_upper = now + timedelta(seconds=self.start_lead)
        max_batch = min(500, max(1, int(os.getenv("OPS_RESERVATION_MAX_BATCH", "200"))))
        response = requests.get(
            self.projection_url,
            headers={
                "X-Gateway-ID": self.projection_gateway_id,
                "X-Reservation-Projection-Token": self.projection_token,
            },
            params={
                "from": window_lower.isoformat().replace("+00:00", "Z"),
                "to": window_upper.isoformat().replace("+00:00", "Z"),
                "limit": max_batch,
            },
            timeout=10,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Reservation projection returned HTTP {response.status_code}")
        body = response.json()
        if not isinstance(body, dict) or str(body.get("gatewayId", "")).strip().lower() != self.projection_gateway_id:
            raise RuntimeError("Reservation projection response is not scoped to this gateway")
        reservations = body.get("reservations")
        if not isinstance(reservations, list):
            raise RuntimeError("Reservation projection response has an invalid reservations field")

        rows: List[Dict[str, Any]] = []
        for item in reservations:
            if not isinstance(item, dict):
                continue
            transaction_hash = str(item.get("transactionHash") or item.get("transaction_hash") or "").strip()
            lab_id = str(item.get("labId") or item.get("lab_id") or "").strip()
            status = str(item.get("status") or "").strip().upper()
            start_time = _parse_reservation_datetime(item.get("startTime") or item.get("start_time"))
            end_time = _parse_reservation_datetime(item.get("endTime") or item.get("end_time"))
            if not transaction_hash or not lab_id or status not in {"CONFIRMED", "ACTIVE"}:
                continue
            if start_time is None or end_time is None:
                logging.warning("Ignoring remote reservation %s with invalid time window", transaction_hash)
                continue
            rows.append({
                "transaction_hash": transaction_hash,
                "lab_id": lab_id,
                "start_time": start_time,
                "end_time": end_time,
                "status": status,
            })
        return rows

    def _select_remote_candidates(
        self,
        conn: Connection,
        rows: Sequence[Mapping[str, Any]],
        now: datetime,
    ) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]]]:
        if not rows:
            return [], []
        reservation_ids = [str(row.get("transaction_hash")) for row in rows if row.get("transaction_hash")]
        successful_actions = set()
        recent_actions = set()
        retry_cutoff = now - timedelta(seconds=self.retry_cooldown)
        operation_query = text(
            """
            SELECT reservation_id, action, success, created_at
            FROM reservation_operations
            WHERE reservation_id IN :reservation_ids
              AND action IN ('scheduler:start', 'scheduler:end')
              AND (success = 1 OR created_at >= :retry_cutoff)
            """
        ).bindparams(bindparam("reservation_ids", expanding=True))
        result = conn.execute(
            operation_query,
            {"reservation_ids": reservation_ids, "retry_cutoff": retry_cutoff},
        )
        for operation in result.mappings():
            key = (str(operation["reservation_id"]), str(operation["action"]))
            if bool(operation["success"]):
                successful_actions.add(key)
            else:
                recent_actions.add(key)

        window_upper = now + timedelta(seconds=self.start_lead)
        window_lower = now - timedelta(seconds=self.lookback)
        ready_time = now - timedelta(seconds=self.end_delay)
        start_rows: List[Mapping[str, Any]] = []
        end_rows: List[Mapping[str, Any]] = []
        for row in rows:
            reservation_id = str(row.get("transaction_hash"))
            status = str(row.get("status") or "").upper()
            start_time = _as_utc_datetime(row.get("start_time"))
            end_time = _as_utc_datetime(row.get("end_time"))
            if (
                status == "CONFIRMED"
                and start_time is not None
                and window_lower <= start_time <= window_upper
                and (reservation_id, "scheduler:start") not in successful_actions
                and (reservation_id, "scheduler:start") not in recent_actions
            ):
                start_rows.append(row)
            if (
                status in {"CONFIRMED", "ACTIVE"}
                and end_time is not None
                and window_lower <= end_time <= ready_time
                and (reservation_id, "scheduler:end") not in successful_actions
                and (reservation_id, "scheduler:end") not in recent_actions
            ):
                end_rows.append(row)
        return start_rows, end_rows

    def _fetch_start_candidates(self, conn: Connection, now: datetime):
        if conn.dialect.name == "mysql":
            conn.execute(text("SET SESSION innodb_lock_wait_timeout = 20"))
        
        window_upper = now + timedelta(seconds=self.start_lead)
        window_lower = now - timedelta(seconds=self.lookback)
        retry_cutoff = now - timedelta(seconds=self.retry_cooldown)
        max_batch = int(os.getenv("OPS_RESERVATION_MAX_BATCH", "200"))
        query = text(
            """
            SELECT transaction_hash, lab_id, start_time, end_time, status
            FROM lab_reservations r
            WHERE r.status = 'CONFIRMED'
              AND r.start_time <= :window_upper
              AND r.start_time >= :window_lower
              AND NOT EXISTS (
                  SELECT 1 FROM reservation_operations o
                  WHERE o.reservation_id = r.transaction_hash
                    AND o.action = 'scheduler:start'
                    AND o.created_at >= :retry_cutoff
              )
            ORDER BY r.start_time ASC
            LIMIT :max_batch
            """
        )
        result = conn.execute(
            query,
            {
                "window_upper": window_upper,
                "window_lower": window_lower,
                "retry_cutoff": retry_cutoff,
                "max_batch": max_batch,
            },
        )
        return result.mappings().all()

    def _fetch_end_candidates(self, conn: Connection, now: datetime):
        if conn.dialect.name == "mysql":
            conn.execute(text("SET SESSION innodb_lock_wait_timeout = 20"))
        
        ready_time = now - timedelta(seconds=self.end_delay)
        window_lower = now - timedelta(seconds=self.lookback)
        retry_cutoff = now - timedelta(seconds=self.retry_cooldown)
        max_batch = int(os.getenv("OPS_RESERVATION_MAX_BATCH", "200"))
        query = text(
            """
            SELECT transaction_hash, lab_id, start_time, end_time, status
            FROM lab_reservations r
            WHERE r.status IN ('CONFIRMED','ACTIVE')
              AND r.end_time <= :ready_time
              AND r.end_time >= :window_lower
              AND NOT EXISTS (
                  SELECT 1 FROM reservation_operations o
                  WHERE o.reservation_id = r.transaction_hash
                    AND o.action = 'scheduler:end'
                    AND o.created_at >= :retry_cutoff
              )
            ORDER BY r.end_time ASC
            LIMIT :max_batch
            """
        )
        result = conn.execute(
            query,
            {
                "ready_time": ready_time,
                "window_lower": window_lower,
                "retry_cutoff": retry_cutoff,
                "max_batch": max_batch,
            },
        )
        return result.mappings().all()

    def _dispatch_start(self, row: Mapping[str, Any]):
        reservation_id = row["transaction_hash"]
        lab_id = row.get("lab_id")
        host = self.registry.get_by_lab(lab_id)
        host_name = (host or {}).get("name") or "unmapped"
        if not host:
            message = f"No host mapping for lab {lab_id}"
            logging.warning("%s", message)
            self._record_scheduler_op(reservation_id, lab_id, host_name, "start", False, message)
            return

        payload = {
            "reservationId": reservation_id,
            "host": host_name,
            "labId": lab_id,
        }
        response, status_code = handle_reservation_start(payload)
        success = bool(response.get("success")) and status_code == 200
        message = None if success else response.get("error") or "Reservation start failed"
        self._record_scheduler_op(
            reservation_id,
            lab_id,
            host_name,
            "start",
            success,
            message,
            payload={"response": response, "status_code": status_code},
            response_code=status_code,
        )
        if success:
            self._update_status(reservation_id, row.get("status"), "ACTIVE")

    def _dispatch_end(self, row: Mapping[str, Any]):
        reservation_id = row["transaction_hash"]
        lab_id = row.get("lab_id")
        host = self.registry.get_by_lab(lab_id)
        host_name = (host or {}).get("name") or "unmapped"
        if not host:
            message = f"No host mapping for lab {lab_id}"
            logging.warning("%s", message)
            self._record_scheduler_op(reservation_id, lab_id, host_name, "end", False, message)
            return

        payload = {
            "reservationId": reservation_id,
            "host": host_name,
            "labId": lab_id,
        }
        response, status_code = handle_reservation_end(payload)
        success = bool(response.get("success")) and status_code == 200
        message = None if success else response.get("error") or "Reservation end failed"
        self._record_scheduler_op(
            reservation_id,
            lab_id,
            host_name,
            "end",
            success,
            message,
            payload={"response": response, "status_code": status_code},
            response_code=status_code,
        )
        if success:
            self._update_status(reservation_id, row.get("status"), "COMPLETED")

    def _record_scheduler_op(
        self,
        reservation_id: str,
        lab_id: Optional[Any],
        host_name: str,
        action_suffix: str,
        success: bool,
        message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        response_code: Optional[int] = None,
    ):
        status = "completed" if success else "failed"
        record_reservation_operation(
            reservation_id,
            str(lab_id) if lab_id is not None else None,
            host_name,
            f"scheduler:{action_suffix}",
            status,
            success,
            response_code=response_code,
            payload=payload,
            message=message,
        )

    def _update_status(self, reservation_id: str, current_status: Optional[str], new_status: str):
        # In projection mode the remote backend is authoritative and the local
        # operation journal provides idempotency. Never mutate a local mirror
        # that may not exist in Lite mode.
        if self.projection_url or not self.engine or not current_status:
            return
        allowed = {
            ("CONFIRMED", "ACTIVE"),
            ("CONFIRMED", "COMPLETED"),
            ("ACTIVE", "COMPLETED"),
            ("CONFIRMED", "CANCELLED"),
            ("ACTIVE", "CANCELLED"),
        }
        if (current_status, new_status) not in allowed:
            logging.debug(
                "Skipping status transition %s -> %s for %s (not allowed)",
                current_status,
                new_status,
                reservation_id,
            )
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE lab_reservations
                        SET status=:new_status, updated_at=UTC_TIMESTAMP()
                        WHERE transaction_hash=:reservation_id AND status=:current_status
                        """
                    ),
                    {
                        "reservation_id": reservation_id,
                        "current_status": current_status,
                        "new_status": new_status,
                    },
                )
        except Exception as exc:
            logging.error(
                "Failed to update reservation %s status to %s: %s",
                reservation_id,
                new_status,
                exc,
            )


RESERVATION_AUTOMATOR = ReservationOrchestrator(DB_ENGINE, HOSTS)


def session_observation_retry_delay_seconds(attempts: int) -> int:
    return min(300, 5 * (2 ** min(max(0, attempts - 1), 6)))


def _encrypt_runtime_secret(value: str) -> str:
    return _load_fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt_runtime_secret(value: str) -> str:
    return _load_fernet().decrypt(value.encode("ascii")).decode("utf-8")


def enqueue_guacamole_token_revocation(payload: Mapping[str, Any]) -> bool:
    if not DB_ENGINE:
        return False
    required = ("authToken", "username", "reservationKey", "jwtJti", "gatewayId", "expiresAt")
    if any(not str(payload.get(field) or "").strip() for field in required):
        return False
    token = str(payload["authToken"]).strip()
    if len(token) > 512:
        return False
    try:
        expires_at = datetime.fromtimestamp(int(payload["expiresAt"]), tz=timezone.utc).replace(tzinfo=None)
        ciphertext = _encrypt_runtime_secret(token)
    except (TypeError, ValueError, OverflowError):
        return False
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    values = {
        "token_hash": token_hash,
        "token_ciphertext": ciphertext,
        "username": str(payload["username"]).strip().lower(),
        "reservation_key": str(payload["reservationKey"]).strip(),
        "jwt_jti": str(payload["jwtJti"]).strip(),
        "gateway_id": str(payload["gatewayId"]).strip(),
        "expires_at": expires_at,
    }
    try:
        with DB_ENGINE.begin() as conn:
            conn.execute(text("""
                INSERT INTO guacamole_token_revocation_queue (
                    token_hash, token_ciphertext, token_validated_at, username, reservation_key,
                    jwt_jti, gateway_id, expires_at, status, next_attempt_at
                ) VALUES (
                    :token_hash, :token_ciphertext, CURRENT_TIMESTAMP, :username, :reservation_key,
                    :jwt_jti, :gateway_id, :expires_at, 'PENDING', CURRENT_TIMESTAMP
                )
            """), values)
        return True
    except IntegrityError:
        try:
            with DB_ENGINE.begin() as conn:
                conn.execute(text("""
                    UPDATE guacamole_token_revocation_queue
                    SET token_ciphertext = :token_ciphertext,
                        token_validated_at = COALESCE(token_validated_at, CURRENT_TIMESTAMP),
                        username = :username,
                        reservation_key = :reservation_key,
                        jwt_jti = :jwt_jti,
                        gateway_id = :gateway_id,
                        expires_at = :expires_at,
                        attempts = CASE WHEN status = 'FAILED' THEN 0 ELSE attempts END,
                        next_attempt_at = CASE
                            WHEN status = 'FAILED' THEN CURRENT_TIMESTAMP
                            ELSE next_attempt_at
                        END,
                        last_error = CASE WHEN status = 'FAILED' THEN NULL ELSE last_error END,
                        status = CASE WHEN status = 'FAILED' THEN 'RETRY' ELSE status END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE token_hash = :token_hash AND status != 'REVOKED'
                """), values)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logging.warning("Guacamole revocation duplicate recovery failed: %s", exc)
            return False
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Guacamole revocation ingest failed: %s", exc)
        return False


@APP.route("/internal/guacamole-token-revocations", methods=["POST"])
def ingest_guacamole_token_revocation():
    if not SESSION_OBSERVATION_INGEST_TOKEN:
        return jsonify({"accepted": False, "error": "Guacamole revocation ingestion is disabled"}), 503
    provided = request.headers.get("X-Gateway-Observation-Token", "")
    if not hmac.compare_digest(provided, SESSION_OBSERVATION_INGEST_TOKEN):
        return jsonify({"accepted": False, "error": "unauthorized"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not enqueue_guacamole_token_revocation(payload):
        return jsonify({"accepted": False, "error": "invalid or unavailable revocation"}), 400
    return jsonify({"accepted": True}), 202


def _guacamole_admin_session() -> Optional[Tuple[str, str]]:
    if not GUAC_ADMIN_USER or not GUAC_ADMIN_PASS:
        return None
    response = requests.post(
        f"{GUAC_API_URL}/tokens",
        data={"username": GUAC_ADMIN_USER, "password": GUAC_ADMIN_PASS},
        timeout=5,
    )
    if response.status_code != 200:
        return None
    body = response.json()
    token = str(body.get("authToken") or "").strip()
    data_source = str(body.get("dataSource") or "mysql").strip()
    return (token, data_source) if token else None


def _guacamole_connection_history_observed(row: Mapping[str, Any]) -> Optional[datetime]:
    """Return the real Guacamole connection start for this token user.

    ``activeConnections`` is only a point-in-time view.  The history table keeps
    a row after a short-lived tunnel closes, which closes the polling gap while
    retaining the token-issued-at boundary needed to avoid matching an older
    session from the same user.
    """
    if not GUACAMOLE_DB_ENGINE:
        return None
    username = str(row.get("username") or "").strip().lower()
    if not username:
        return None
    issued_at = to_utc(row.get("token_validated_at") or row.get("created_at"))
    expires_at = to_utc(row.get("expires_at"))
    if not issued_at or not expires_at:
        return None
    window_start = issued_at - timedelta(seconds=GUACAMOLE_HISTORY_LOOKBACK_SECONDS)
    try:
        with GUACAMOLE_DB_ENGINE.connect() as conn:
            found = conn.execute(
                text("""
                    SELECT start_date
                    FROM guacamole_connection_history
                    WHERE LOWER(username) = :username
                      AND start_date >= :window_start
                      AND start_date <= :expires_at
                      AND (end_date IS NULL OR end_date >= :window_start)
                    ORDER BY start_date ASC
                    LIMIT 1
                """),
                {
                    "username": username,
                    "window_start": window_start.replace(tzinfo=None),
                    "expires_at": expires_at.replace(tzinfo=None),
                },
            ).first()
            return to_utc(found[0]) if found is not None else None
    except Exception as exc:  # pylint: disable=broad-except
        # Older Guacamole schemas may not expose connection history.  The
        # activeConnections path remains a valid fallback in that case.
        logging.debug("Unable to query Guacamole connection history: %s", exc)
        return None


def _reconcile_guacamole_observations(admin_token: str, data_source: str) -> None:
    if not DB_ENGINE:
        return
    response = requests.get(
        f"{GUAC_API_URL}/session/data/{quote(data_source, safe='')}/activeConnections",
        params={"token": admin_token},
        timeout=5,
    )
    if response.status_code != 200:
        return
    active_users = {
        str(connection.get("username") or "").strip().lower()
        for connection in (response.json() or {}).values()
        if isinstance(connection, dict)
    }
    evidence_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS
    )
    with DB_ENGINE.begin() as conn:
        rows = conn.execute(text("""
            SELECT token_hash, token_ciphertext, token_validated_at, reservation_key,
                   jwt_jti, gateway_id, username, created_at, expires_at, status
            FROM guacamole_token_revocation_queue
            WHERE status IN ('PENDING', 'RETRY', 'REVOKED')
              AND observed_at IS NULL
              AND expires_at > :evidence_cutoff
            ORDER BY created_at ASC
            LIMIT 100
        """), {"evidence_cutoff": evidence_cutoff}).mappings().all()
    for row in rows:
        history_row: Dict[str, Any] = {str(key): value for key, value in row.items()}
        history_started_at = _guacamole_connection_history_observed(history_row)
        active_observed = str(row["username"]).lower() in active_users
        if not active_observed and history_started_at is None:
            continue
        historical_after_revocation = (
            str(row.get("status") or "").upper() == "REVOKED"
            and history_started_at is not None
            and row.get("token_validated_at") is not None
        )
        if not historical_after_revocation:
            try:
                user_token = _decrypt_runtime_secret(str(row["token_ciphertext"]))
                token_response = requests.get(
                    f"{GUAC_API_URL}/session/data/{quote(data_source, safe='')}",
                    params={"token": user_token},
                    timeout=5,
                )
                # Before revocation, the exact token must still be accepted.
                # After revocation, a pre-revocation validation marker plus a
                # matching historical connection is the durable proof.
                if token_response.status_code != 200:
                    continue
            except Exception as exc:  # pylint: disable=broad-except
                logging.warning("Unable to validate Guacamole token: %s", exc)
                continue
        observed_at = history_started_at or datetime.now(timezone.utc)
        accepted = enqueue_session_observation({
            "dedupKey": row["token_hash"],
            "reservationKey": row["reservation_key"],
            "jwtJti": row["jwt_jti"],
            "sessionId": f"guac:{row['token_hash']}",
            "gatewayId": row["gateway_id"],
            "accessType": "guacamole",
            "observedAt": int(observed_at.timestamp()),
        })
        if accepted:
            with DB_ENGINE.begin() as conn:
                conn.execute(text("""
                    UPDATE guacamole_token_revocation_queue
                    SET observed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE token_hash = :token_hash AND observed_at IS NULL
                """), {"token_hash": row["token_hash"]})


def process_guacamole_token_revocations() -> int:
    if not DB_ENGINE:
        return 0
    session = _guacamole_admin_session()
    if not session:
        logging.warning("Guacamole token revocation deferred: admin session unavailable")
        return 0
    admin_token, data_source = session
    try:
        _reconcile_guacamole_observations(admin_token, data_source)
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Guacamole session observation reconciliation failed: %s", exc)
    with DB_ENGINE.begin() as conn:
        rows = conn.execute(text("""
            SELECT token_hash, token_ciphertext, attempts
            FROM guacamole_token_revocation_queue
            WHERE status IN ('PENDING', 'RETRY')
              AND expires_at <= CURRENT_TIMESTAMP
              AND next_attempt_at <= CURRENT_TIMESTAMP
            ORDER BY expires_at ASC
            LIMIT 100
        """)).mappings().all()
    revoked = 0
    for row in rows:
        attempts = int(row["attempts"] or 0) + 1
        try:
            user_token = _decrypt_runtime_secret(str(row["token_ciphertext"]))
            response = requests.delete(
                f"{GUAC_API_URL}/tokens/{quote(user_token, safe='')}",
                params={"token": admin_token},
                timeout=5,
            )
            if response.status_code not in (204, 404):
                raise RuntimeError(f"Guacamole token delete returned {response.status_code}")
            with DB_ENGINE.begin() as conn:
                conn.execute(text("""
                    UPDATE guacamole_token_revocation_queue
                    SET status = 'REVOKED', attempts = :attempts,
                        revoked_at = CURRENT_TIMESTAMP, last_error = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE token_hash = :token_hash
                """), {"token_hash": row["token_hash"], "attempts": attempts})
            revoked += 1
        except Exception as exc:  # pylint: disable=broad-except
            status = "FAILED" if attempts >= GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS else "RETRY"
            logging.warning("Guacamole token revocation failed for %s: %s", row["token_hash"], exc)
            next_attempt = datetime.now(timezone.utc) + timedelta(
                seconds=session_observation_retry_delay_seconds(attempts)
            )
            with DB_ENGINE.begin() as conn:
                conn.execute(text("""
                    UPDATE guacamole_token_revocation_queue
                    SET status = :status, attempts = :attempts,
                        next_attempt_at = :next_attempt_at, last_error = :last_error,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE token_hash = :token_hash
                """), {
                    "status": status,
                    "attempts": attempts,
                    "next_attempt_at": next_attempt,
                    "last_error": "Guacamole token revocation failed",
                    "token_hash": row["token_hash"],
                })
    return revoked


def enqueue_session_observation(payload: Mapping[str, Any]) -> bool:
    """Persist evidence produced after a runtime confirms an active session."""
    if not DB_ENGINE:
        return False
    required_fields = (
        "dedupKey", "reservationKey", "jwtJti", "sessionId", "gatewayId", "accessType", "observedAt",
    )
    if any(not str(payload.get(field) or "").strip() for field in required_fields):
        return False
    try:
        observed_at = datetime.fromtimestamp(int(payload["observedAt"]), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError):
        return False
    try:
        with DB_ENGINE.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO gateway_session_observation_outbox (
                        dedup_key, reservation_key, jwt_jti, session_id, gateway_id,
                        access_type, observed_at, status, next_attempt_at
                    ) VALUES (
                        :dedup_key, :reservation_key, :jwt_jti, :session_id, :gateway_id,
                        :access_type, :observed_at, 'PENDING', CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "dedup_key": str(payload["dedupKey"]).strip(),
                    "reservation_key": str(payload["reservationKey"]).strip(),
                    "jwt_jti": str(payload["jwtJti"]).strip(),
                    "session_id": str(payload["sessionId"]).strip(),
                    "gateway_id": str(payload["gatewayId"]).strip(),
                    "access_type": str(payload["accessType"]).strip().lower(),
                    "observed_at": observed_at,
                },
            )
        return True
    except IntegrityError:
        # A repeated WebSocket observation is idempotent. A terminal delivery
        # is reopened only when the trusted gateway observes the same session again.
        try:
            with DB_ENGINE.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE gateway_session_observation_outbox
                        SET attempts = CASE WHEN status = 'FAILED' THEN 0 ELSE attempts END,
                            next_attempt_at = CASE
                                WHEN status IN ('FAILED', 'RETRY') THEN CURRENT_TIMESTAMP
                                ELSE next_attempt_at
                            END,
                            locked_at = CASE WHEN status = 'FAILED' THEN NULL ELSE locked_at END,
                            last_error = CASE WHEN status = 'FAILED' THEN NULL ELSE last_error END,
                            status = CASE WHEN status = 'FAILED' THEN 'RETRY' ELSE status END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE dedup_key = :dedup_key
                        """
                    ),
                    {"dedup_key": str(payload["dedupKey"]).strip()},
                )
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logging.warning("Session observation duplicate recovery failed: %s", exc)
            return False
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Session observation outbox ingest failed: %s", exc)
        return False


@APP.route("/internal/session-observations", methods=["POST"])
def ingest_session_observation():
    """Accept observations only from the co-located OpenResty gateway."""
    if not SESSION_OBSERVATION_INGEST_TOKEN:
        return jsonify({"accepted": False, "error": "session observation ingestion is disabled"}), 503
    provided = request.headers.get("X-Gateway-Observation-Token", "")
    if not hmac.compare_digest(provided, SESSION_OBSERVATION_INGEST_TOKEN):
        return jsonify({"accepted": False, "error": "unauthorized"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not enqueue_session_observation(payload):
        return jsonify({"accepted": False, "error": "invalid or unavailable observation"}), 400
    return jsonify({"accepted": True}), 202


def _claim_session_observation_outbox_rows() -> List[Dict[str, Any]]:
    if not DB_ENGINE:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    try:
        with DB_ENGINE.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE gateway_session_observation_outbox
                    SET status = 'RETRY', next_attempt_at = CURRENT_TIMESTAMP,
                        locked_at = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE status = 'SENDING' AND locked_at < :cutoff
                    """
                ),
                {"cutoff": cutoff},
            )
            rows = conn.execute(
                text(
                    """
                    SELECT id, reservation_key, jwt_jti, session_id, gateway_id,
                           access_type, observed_at, attempts
                    FROM gateway_session_observation_outbox
                    WHERE status IN ('PENDING', 'RETRY')
                      AND next_attempt_at <= CURRENT_TIMESTAMP
                    ORDER BY next_attempt_at ASC, id ASC
                    LIMIT :limit
                    """
                ),
                {"limit": SESSION_OBSERVATION_OUTBOX_BATCH_SIZE},
            ).mappings().all()
            claimed = []
            for row in rows:
                updated = conn.execute(
                    text(
                        """
                        UPDATE gateway_session_observation_outbox
                        SET status = 'SENDING', locked_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id AND status IN ('PENDING', 'RETRY')
                        """
                    ),
                    {"id": row["id"]},
                ).rowcount
                if updated == 1:
                    claimed.append(dict(row))
            return claimed
    except Exception as exc:  # pylint: disable=broad-except
        logging.warning("Session observation outbox claim failed: %s", exc)
        return []


def _mark_session_observation_delivered(record_id: int) -> None:
    if not DB_ENGINE:
        return
    with DB_ENGINE.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE gateway_session_observation_outbox
                SET status = 'SENT', delivered_at = CURRENT_TIMESTAMP,
                    locked_at = NULL, last_error = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND status = 'SENDING'
                """
            ),
            {"id": record_id},
        )


def _mark_session_observation_failure(record: Mapping[str, Any], error: str) -> None:
    if not DB_ENGINE:
        return
    attempts = int(record.get("attempts") or 0) + 1
    status = "FAILED" if attempts >= SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS else "RETRY"
    next_attempt = datetime.now(timezone.utc) + timedelta(
        seconds=session_observation_retry_delay_seconds(attempts)
    )
    with DB_ENGINE.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE gateway_session_observation_outbox
                SET status = :status, attempts = :attempts,
                    next_attempt_at = :next_attempt_at, locked_at = NULL,
                    last_error = :last_error, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND status = 'SENDING'
                """
            ),
            {
                "id": record["id"],
                "status": status,
                "attempts": attempts,
                "next_attempt_at": next_attempt,
                "last_error": str(error)[:1024],
            },
        )


def _session_observed_epoch(value: Any) -> int:
    if isinstance(value, datetime):
        return int((value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp())
    parsed = to_utc(value)
    if parsed:
        return int(parsed.timestamp())
    return int(time.time())


def _base64url_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")


def _session_observer_authorization() -> str:
    """Create a short-lived JWT scoped only to session-observation submission."""
    if not SESSION_OBSERVER_GATEWAY_ID or not SESSION_OBSERVER_SIGNING_SECRET:
        raise RuntimeError("session observer gateway credentials are not configured")
    padding = "=" * (-len(SESSION_OBSERVER_SIGNING_SECRET) % 4)
    key = base64.urlsafe_b64decode(SESSION_OBSERVER_SIGNING_SECRET + padding)
    if len(key) < 32:
        raise RuntimeError("session observer signing secret must contain at least 32 bytes")
    now = int(time.time())
    header = _base64url_json({"alg": "HS256", "typ": "JWT"})
    payload = _base64url_json({
        "iss": SESSION_OBSERVER_GATEWAY_ID,
        "sub": SESSION_OBSERVER_GATEWAY_ID,
        "aud": "session-observation",
        "scope": "session-observation:submit",
        "iat": now,
        "exp": now + 60,
        "jti": base64.urlsafe_b64encode(os.urandom(18)).rstrip(b"=").decode("ascii"),
    })
    signing_input = f"{header}.{payload}"
    signature = base64.urlsafe_b64encode(
        hmac.new(key, signing_input.encode("ascii"), hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    return f"Bearer {signing_input}.{signature}"


def deliver_session_observation_outbox() -> int:
    """Deliver durable runtime-confirmed observations to blockchain-services."""
    if not SESSION_OBSERVATION_OUTBOX_ENABLED or not DB_ENGINE:
        return 0
    if not ACCESS_AUDIT_URL:
        logging.error("Session observation outbox is pending: ACCESS_AUDIT_URL must target the issuing Full gateway")
        return 0
    if not SESSION_OBSERVER_GATEWAY_ID or not SESSION_OBSERVER_SIGNING_SECRET:
        logging.error("Session observation outbox is pending: session observer credentials are not configured")
        return 0

    delivered = 0
    for record in _claim_session_observation_outbox_rows():
        try:
            authorization = _session_observer_authorization()
        except Exception as exc:  # pylint: disable=broad-except
            logging.warning("Observer authorization failed: %s", exc)
            _mark_session_observation_failure(record, "Observer authorization failed")
            continue
        reported_at = int(time.time())
        payload = {
            "reservationKey": record["reservation_key"],
            "jwtJti": record["jwt_jti"],
            "sessionId": record["session_id"],
            "gatewayId": SESSION_OBSERVER_GATEWAY_ID,
            "accessType": record["access_type"],
            "observedAt": _session_observed_epoch(record["observed_at"]),
            "reportedAt": reported_at,
        }
        try:
            response = requests.post(
                ACCESS_AUDIT_URL,
                json=payload,
                headers={"Authorization": authorization},
                timeout=SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS,
            )
            body = response.json() if response.content else {}
            if 200 <= response.status_code < 300 and body.get("recorded") is True:
                _mark_session_observation_delivered(record["id"])
                delivered += 1
            else:
                _mark_session_observation_failure(
                    record,
                    f"audit endpoint status={response.status_code} recorded={body.get('recorded')!r}",
                )
        except Exception as exc:  # pylint: disable=broad-except
            logging.warning("Audit delivery failed: %s", exc)
            _mark_session_observation_failure(record, "Audit delivery failed")
    return delivered


def _replace_host_registry(registry: HostRegistry) -> None:
    global HOSTS
    with HOSTS_LOCK:
        HOSTS = registry
        RESERVATION_AUTOMATOR.registry = registry


def reload_hosts() -> Tuple[int, Optional[str]]:
    """Reload host catalog from CONFIG_PATH."""
    return _reload_hosts_impl(
        load_config=load_config,
        registry_factory=HostRegistry,
        refresh_trust_store=refresh_winrm_trust_store,
        replace_registry=_replace_host_registry,
        logger=logging,
    )


def start_scheduler():
    scheduler = BackgroundScheduler(daemon=True)
    jobs = 0

    if os.getenv("OPS_POLL_ENABLED", "false").lower() == "true":
        interval = int(os.getenv("OPS_POLL_INTERVAL", "60"))
        scheduler.add_job(
            poll_all_hosts,
            "interval",
            seconds=interval,
            next_run_time=datetime.now(timezone.utc),
            id="heartbeat-poller",
            replace_existing=True,
        )
        jobs += 1
        logging.info("Heartbeat poller enabled (interval %ss)", interval)

    jobs += RESERVATION_AUTOMATOR.register(scheduler)

    if GUACAMOLE_TEMP_USER_CLEANUP_ENABLED:
        scheduler.add_job(
            cleanup_expired_guacamole_temp_users,
            "interval",
            seconds=GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS,
            next_run_time=datetime.now(timezone.utc),
            id="guacamole-temp-user-cleanup",
            replace_existing=True,
        )
        jobs += 1
        logging.info(
            "Guacamole temporary user cleanup enabled (interval %ss)",
            GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS,
        )

    if SESSION_OBSERVATION_OUTBOX_ENABLED:
        scheduler.add_job(
            deliver_session_observation_outbox,
            "interval",
            seconds=SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS,
            next_run_time=datetime.now(timezone.utc),
            id="session-observation-outbox",
            replace_existing=True,
        )
        jobs += 1
        logging.info(
            "Session observation outbox enabled (interval %ss)",
            SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS,
        )

    scheduler.add_job(
        process_guacamole_token_revocations,
        "interval",
        seconds=GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS,
        next_run_time=datetime.now(timezone.utc),
        id="guacamole-token-revocation",
        replace_existing=True,
    )
    jobs += 1
    logging.info(
        "Durable Guacamole token revocation enabled (interval %ss)",
        GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS,
    )

    if jobs == 0:
        logging.info("Scheduler not started (no jobs enabled)")
        return

    scheduler.start()
    logging.info("Scheduler started with %s job(s)", jobs)


def configure_logging():
    level = os.getenv("OPS_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def main():
    configure_logging()
    refresh_winrm_trust_store(HOSTS.all_hosts())
    start_scheduler()
    bind = os.getenv("OPS_BIND", "0.0.0.0")
    port = int(os.getenv("OPS_PORT", "8081"))
    serve(APP, host=bind, port=port)


if __name__ == "__main__":
    main()
