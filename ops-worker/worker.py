#!/usr/bin/env python3
"""
Ops worker: WoL + WinRM wrapper + heartbeat poller for Lab Station hosts.
Exposes a small Flask API and optional scheduler.
"""
import errno
import json
import hmac
import ipaddress
import logging
import os
import socket
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional, Pattern, Sequence, Set, Tuple, Union, cast

from cryptography.fernet import Fernet, InvalidToken
from flask import Response, jsonify, request, stream_with_context
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
import wakeonlan as _wakeonlan
import requests
import winrm
from app_factory import create_app, register_blueprints
from entrypoint import (
    configure_logging as _configure_logging_impl,
    run as _run_entrypoint_impl,
)
from entrypoint_runtime import create_entrypoint_runtime
from entrypoint_context import EntrypointContext
from app_hooks import (
    check_ops_internal_auth as _check_ops_internal_auth_impl,
    handle_unexpected_exception as _handle_unexpected_exception_impl,
    internal_error_response as _internal_error_response_impl,
    request_id_from_headers as _request_id_from_headers_impl,
    requires_ops_internal_auth as _requires_ops_internal_auth_impl,
    sanitize_log_value as _sanitize_log_value_impl,
)
from app_hooks_runtime import create_app_hooks_runtime
from app_hooks_context import AppHooksContext
from runtime_context import RuntimeContext
from runtime_composition import compose_worker_app
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from apscheduler.schedulers.background import BackgroundScheduler
from waitress import serve
import aas_generator
from errors import (
    WINRM_AUTH_FAILED_CODE,
    WINRM_AUTH_FAILED_MESSAGE,
    WINRM_CERTIFICATE_EXPIRED_MESSAGE,
    WINRM_CERTIFICATE_INVALID_MESSAGE,
    WINRM_CERTIFICATE_NOT_YET_VALID_MESSAGE,
    WINRM_CERTIFICATE_REQUIRED_MESSAGE,
    WINRM_CREDENTIALS_REQUIRED_MESSAGE,
    WINRM_FINGERPRINT_CONFIRMATION_REQUIRED_MESSAGE,
    WINRM_FINGERPRINT_MISMATCH_MESSAGE,
    WINRM_HEARTBEAT_INVALID_CODE,
    WINRM_HEARTBEAT_INVALID_MESSAGE,
    WINRM_HEARTBEAT_NOT_FOUND_CODE,
    WINRM_HEARTBEAT_NOT_FOUND_MESSAGE,
    WINRM_TLS_FAILED_MESSAGE,
    WINRM_TRUST_ERROR_MESSAGES,
    WINRM_TRUST_REF_MISMATCH_MESSAGE,
    WINRM_TRUST_REQUIRED_CODE,
    WINRM_TRUST_REQUIRED_MESSAGE,
    WINRM_UNREACHABLE_CODE,
    WINRM_UNREACHABLE_MESSAGE,
    WinRMHeartbeatError,
    WinRMRemoteFileNotFoundError,
    WinRMTrustError,
    build_winrm_trust_error_payload as _build_winrm_trust_error_payload_impl,
    is_missing_winrm_credentials_error,
)
from winrm_trust import (
    _certificate_datetime,
    _certificate_matches_host,
    _dns_name_matches,
    _format_certificate_datetime,
    _is_valid_ip_address,
    _parse_winrm_certificate_bytes as _parse_winrm_certificate_bytes_impl,
    normalize_trust_ref as _normalize_trust_ref_impl,
    resolve_trust_file_path as _resolve_trust_file_path_impl,
    resolve_trust_root as _resolve_trust_root_impl,
    _resolve_winrm_trust_file_path,
    trust_ref_for_host as _trust_ref_for_host_impl,
    _winrm_certificate_metadata,
    validate_winrm_certificate as _validate_winrm_certificate_impl,
    WINRM_CERTIFICATE_MAX_BYTES as _WINRM_CERTIFICATE_MAX_BYTES_DEFAULT,
)
from winrm_trust_store import (
    delete_trust_files as _delete_trust_files_impl,
    materialize_trust_pem as _materialize_trust_pem_impl,
    read_trust_certificate as _read_trust_certificate_impl,
    read_trust_metadata as _read_trust_metadata_file,
    write_trust_bytes as _write_trust_bytes_impl,
    write_trust_metadata as _write_trust_metadata_file,
)
from winrm_trust_service import inspect_winrm_trust as _inspect_winrm_trust_impl
from winrm_trust_operations import (
    certificate_response_metadata as _certificate_response_metadata_impl,
    delete_trust_certificate as _delete_trust_certificate_impl,
    read_certificate_upload as _read_certificate_upload_impl,
    request_value as _trust_request_value_impl,
    store_trust_certificate as _store_trust_certificate_impl,
    trust_http_status as _trust_http_status_impl,
)
from winrm_trust_runtime import create_winrm_trust_runtime
from winrm_trust_context import WinRMTrustContext
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
from heartbeat_context import HeartbeatContext
from heartbeat_runtime import create_heartbeat_runtime
from winrm_credentials_resolution import (
    credential_ref_for_host as _credential_ref_for_host_impl,
    normalize_credential_ref as _normalize_credential_ref_impl,
    resolve_winrm_credentials as _resolve_winrm_credentials_impl,
)
from host_catalog import (
    catalog_bool as _catalog_bool_impl,
    resolve_addresses as _resolve_addresses_impl,
    validate_winrm_catalog as _validate_winrm_catalog_impl,
)
from host_registry import HostRegistry
from host_config_service import (
    load_dynamic_config as _load_dynamic_config_impl,
    load_host_config as _load_host_config_impl,
    resolve_host_secret_refs as _resolve_host_secret_refs_impl,
    update_dynamic_host as _update_dynamic_host_impl,
    upsert_dynamic_host as _upsert_dynamic_host_impl,
    write_dynamic_config as _write_dynamic_config_impl,
)
from host_config_runtime import create_host_config_runtime
from host_config_context import HostConfigContext
from host_reload_service import reload_hosts as _reload_hosts_impl
from host_reload_runtime import create_host_reload_runtime
from host_reload_context import HostReloadContext
from host_inventory_context import HostInventoryContext
from host_inventory_runtime import create_host_inventory_runtime
from host_discovery_values import (
    probe_labstation_http as _probe_labstation_http_impl,
    response_looks_like_labstation as _response_looks_like_labstation_impl,
)
from host_discovery_service import (
    discover_labstation_candidate as _discover_labstation_candidate_impl,
)
from host_discovery_runtime import create_host_discovery_runtime
from host_discovery_context import HostDiscoveryContext
from host_heartbeat_discovery import (
    discover_heartbeat_hint as _discover_heartbeat_hint_impl,
)
from host_heartbeat_paths import (
    build_heartbeat_path_candidates as _build_heartbeat_path_candidates_impl,
    query_labstation_task_heartbeat_path as _query_labstation_task_heartbeat_path_impl,
)
from guacamole_connection_lookup import (
    guacamole_name_candidates as _guacamole_name_candidates_impl,
    normalize_match_key as _normalize_match_key_impl,
    resolve_guacamole_connection as _resolve_guacamole_connection_impl,
)
from guacamole_connection_values import (
    parse_guacamole_selector as _parse_guacamole_selector_impl,
    safe_connection_response as _safe_connection_response_impl,
)
from guacamole_catalog_service import (
    load_guacamole_connections as _load_guacamole_connections_impl,
)
from lab_resolution_composition import create_lab_resolution_composition
from guacamole_runtime import create_guacamole_runtime
from guacamole_context import GuacamoleContext
from guacamole_dsn import build_guacamole_dsn as _build_guacamole_dsn_impl
from ops_dsn import build_ops_dsn as _build_ops_dsn_impl
from datetime_values import (
    as_utc_datetime as _as_utc_datetime_impl,
    to_iso as _to_iso_impl,
)
from input_values import (
    coerce_bool as _coerce_bool_impl,
    normalize_args as _normalize_args_impl,
    parse_bool as _parse_bool_impl,
    parse_recipients as _parse_recipients_impl,
)
from input_context import InputContext
from input_runtime import create_input_runtime
from database_health import database_is_usable as _database_is_usable_impl
from database_context import DatabaseContext
from database_runtime import create_database_runtime
from demo_values import (
    canonical_demo_lab_id as _canonical_demo_lab_id_impl,
    get_mandatory_field as _get_mandatory_field_impl,
)
from demo_readiness_service import build_demo_readiness as _build_demo_readiness_impl
from demo_operations import (
    build_demo_context as _build_demo_context_impl,
    handle_demo_end as _handle_demo_end_impl,
    handle_demo_event as _handle_demo_event_impl,
    handle_demo_start as _handle_demo_start_impl,
    host_is_ready as _demo_host_is_ready_impl,
    operation_completed as _demo_operation_completed_impl,
    record_demo_event as _record_demo_event_impl,
)
from demo_runtime import create_demo_runtime
from demo_context import DemoContext
from host_catalog_io import (
    merge_host_configs as _merge_host_configs_impl,
    read_hosts_config as _read_hosts_config_impl,
)
from wol_service import wol_and_wait as _wol_and_wait_impl
from wol_context import WolContext
from wol_runtime import create_wol_runtime
from network_probe import (
    host_is_up as _host_is_up_impl,
    is_valid_ping_target as _is_valid_ping_target_impl,
    tcp_port_open as _tcp_port_open_impl,
)
from operation_persistence import (
    record_reservation_operation as _record_reservation_operation_impl,
)
from notification_service import (
    check_failure_alert as _check_failure_alert_impl,
    notify_critical_failure as _notify_critical_failure_impl,
    send_failure_alert as _send_failure_alert_impl,
    should_send_failure_alert as _should_send_failure_alert_impl,
)
from timeline_service import (
    build_reservation_timeline as _build_reservation_timeline_impl,
    fetch_latest_heartbeat as _fetch_latest_heartbeat_impl,
    sanitize_limit as _sanitize_limit_impl,
    sanitize_offset as _sanitize_offset_impl,
    summarize_phases as _summarize_phases_impl,
)
from timeline_runtime import create_timeline_runtime
from timeline_context import TimelineContext
from local_mode_route import get_local_mode_flag_path as _get_local_mode_flag_path_impl
from guacamole_provision_service import (
    cleanup_expired_temporary_users as _cleanup_guacamole_users_impl,
    delete_temporary_user as _delete_guacamole_user_impl,
    provision_temporary_user as _provision_guacamole_user_impl,
)
from guacamole_provision_route import (
    check_guacamole_provisioner_auth as _check_guacamole_provisioner_auth_impl,
)
from reservation_runtime import create_reservation_orchestrator_class
from reservation_context import ReservationRuntimeContext
from winrm_runtime import create_winrm_runtime
from winrm_context import WinRMContext
from reservation_operations import (
    handle_reservation_end as _handle_reservation_end_impl,
    handle_reservation_start as _handle_reservation_start_impl,
)
from reservation_lifecycle_runtime import create_reservation_lifecycle_runtime
from reservation_lifecycle_context import ReservationLifecycleContext
from reservation_execution_runtime import create_reservation_execution_runtime
from reservation_execution_context import ReservationExecutionContext
from reservation_steps import (
    perform_command_step as _perform_command_step_impl,
    perform_wake_step as _perform_wake_step_impl,
)
from session_observations import (
    SessionObservations,
    default_retry_delay_seconds as _default_retry_delay_seconds_impl,
)
from session_observation_runtime import create_session_observation_runtime
from session_observation_context import SessionObservationContext
from health_values import build_health_response as _build_health_response_impl
from operation_values import rows_to_operations as _rows_to_operations_impl
from host_provisioning_context import HostProvisioningContext
from host_provisioning_runtime import create_host_provisioning_runtime
from runtime_values import (
    DEFAULT_LABSTATION_EXE,
    ENOUGH_DISCOVERY_SIGNALS,
    GUAC_SELECTOR_RE,
    HOST_NAME_RE,
    HTTP_HEADER_NAME_RE,
    MAC_RE,
    WINRM_CERTIFICATE_EXTENSIONS,
    WINRM_PORT,
    WINRM_TRUST_CERTIFICATE_NAME,
    WINRM_TRUST_METADATA_NAME,
    WINRM_TRUST_PEM_NAME,
    WINRM_TRUST_REF_RE,
)
from secret_values import env_or_secret_file as _env_or_secret_file_impl
from runtime_config import (
    is_lite_gateway as _is_lite_gateway_config_impl,
    load_runtime_paths,
    load_runtime_policy,
    publish_runtime_paths,
    publish_runtime_policy,
)
from runtime_state import (
    create_runtime_state,
    replace_host_registry as _replace_host_registry_impl,
)
from worker_compatibility_runtime import create_worker_compatibility_runtime
from worker_compatibility_context import WorkerCompatibilityContext
from runtime_services import create_runtime_services
from power_runtime_factory import create_power_runtime
from power_reservation_service import (
    execute_reservation_power_phase as _execute_reservation_power_phase_impl,
    host_local_mode_enabled as _host_local_mode_enabled_impl,
    project_power_operation as _project_power_operation_impl,
)
from winrm_credential_store import (
    decrypt_secret as _decrypt_secret_impl,
    encrypt_secret as _encrypt_secret_impl,
    fernet_key_is_usable as _fernet_key_is_usable_impl,
    load_credentials as _load_credentials_store_impl,
    load_fernet as _load_fernet_store_impl,
    read_credentials_store as _read_credentials_store_impl,
    save_credentials as _save_credentials_store_impl,
    write_credentials_store as _write_credentials_store_impl,
)
from credential_runtime import create_credential_runtime
from credential_context import CredentialContext
from scheduler_service import start_scheduler as _start_scheduler_impl
from scheduler_runtime import create_scheduler_runtime
from scheduler_context import SchedulerContext
from power.api import power_bp
from power.models import ValidationError as PowerValidationError
from power.credentials import PowerCredentialStore
from power.persistence import PowerOperationStore
from power.service import PowerRuntime


def wake(mac: str, *, host: str, port: int) -> None:
    """Send a WoL packet across wakeonlan package API versions."""
    sender = getattr(_wakeonlan, "wake", None)
    if callable(sender):
        sender(mac, host=host, port=port)
        return
    _wakeonlan.send_magic_packet(mac, ip_address=host, port=port)


# These aliases are installed by runtime factories below their dependency
# contexts. Keep their callable contracts explicit so static analyzers can
# understand the composition root without evaluating runtime publication.
_env_or_secret_file: Callable[..., str]
_sanitize_log_value: Callable[[Any], str]
_request_id: Callable[[], str]
internal_error_response: Callable[..., Any]
_requires_ops_internal_auth: Callable[[str], bool]
_fetch_latest_heartbeat: Callable[[Any, str], Optional[Dict[str, Any]]]
normalize_match_key: Callable[[Optional[Any]], str]
normalize_winrm_trust_ref: Callable[[Any], str]
handle_reservation_start: Callable[[Dict[str, Any]], Tuple[Dict[str, Any], int]]
handle_reservation_end: Callable[[Dict[str, Any]], Tuple[Dict[str, Any], int]]
_execute_reservation_power_phase: Callable[
    [str, Optional[str], Mapping[str, Any], str, Dict[str, Any]],
    Dict[str, Any],
]
perform_wake_step: Callable[
    [Mapping[str, Any], str, Optional[str], Dict[str, Any]],
    Tuple[bool, Dict[str, Any]],
]
normalize_mac: Callable[[Any], str]
load_guacamole_connections: Callable[
    [], Tuple[List[Dict[str, Any]], Optional[str]]
]
parse_guacamole_selector: Callable[..., Any]


def _publish_host_registry(registry: Any) -> None:
    global HOSTS
    HOSTS = registry


_WORKER_COMPATIBILITY_CONTEXT = WorkerCompatibilityContext(
    get_is_lite_gateway_impl=lambda: _is_lite_gateway_config_impl,
    get_environ=lambda: os.environ,
    get_datetime=lambda: datetime,
    get_timezone=lambda: timezone,
    get_hosts=lambda: HOSTS,
    get_jsonify=lambda: jsonify,
    get_hosts_lock=lambda: HOSTS_LOCK,
    get_replace_host_registry_impl=lambda: _replace_host_registry_impl,
    get_reservation_automator=lambda: RESERVATION_AUTOMATOR,
    set_host_registry=_publish_host_registry,
)
_WORKER_COMPATIBILITY_RUNTIME = create_worker_compatibility_runtime(
    _WORKER_COMPATIBILITY_CONTEXT
)
_is_lite_gateway = _WORKER_COMPATIBILITY_RUNTIME.is_lite_gateway
_now_utc = _WORKER_COMPATIBILITY_RUNTIME.now_utc
_winrm_trust_host_or_404 = _WORKER_COMPATIBILITY_RUNTIME.winrm_trust_host_or_404
_replace_host_registry = _WORKER_COMPATIBILITY_RUNTIME.replace_host_registry
_set_host_registry = _WORKER_COMPATIBILITY_RUNTIME.set_host_registry

_APP_HOOKS_CONTEXT = AppHooksContext(
    get_env_or_secret_file_impl=lambda: _env_or_secret_file_impl,
    get_logger=lambda: logging,
    get_sanitize_log_value_impl=lambda: _sanitize_log_value_impl,
    get_as_utc_datetime_impl=lambda: _as_utc_datetime_impl,
    get_datetime=lambda: datetime,
    get_timezone=lambda: timezone,
    get_request_headers=lambda: request.headers,
    get_request_path=lambda: request.path,
    get_request_id_from_headers_impl=lambda: _request_id_from_headers_impl,
    get_internal_error_response_impl=lambda: _internal_error_response_impl,
    get_request_id=lambda: _request_id,
    get_sanitize_log_value=lambda: _sanitize_log_value,
    get_handle_unexpected_exception_impl=lambda: _handle_unexpected_exception_impl,
    get_internal_error_response=lambda: internal_error_response,
    get_requires_ops_internal_auth_impl=lambda: _requires_ops_internal_auth_impl,
    get_check_ops_internal_auth_impl=lambda: _check_ops_internal_auth_impl,
    get_ops_internal_auth_header=lambda: OPS_INTERNAL_AUTH_HEADER,
    get_ops_internal_auth_token=lambda: OPS_INTERNAL_AUTH_TOKEN,
    get_requires_ops_internal_auth=lambda: _requires_ops_internal_auth,
    get_jsonify=lambda: jsonify,
)
_APP_HOOKS_RUNTIME = create_app_hooks_runtime(_APP_HOOKS_CONTEXT)
_env_or_secret_file = _APP_HOOKS_RUNTIME.env_or_secret_file
_sanitize_log_value = _APP_HOOKS_RUNTIME.sanitize_log_value
_as_utc_datetime = _APP_HOOKS_RUNTIME.as_utc_datetime
_parse_reservation_datetime = _APP_HOOKS_RUNTIME.parse_reservation_datetime
_request_id = _APP_HOOKS_RUNTIME.request_id
internal_error_response = _APP_HOOKS_RUNTIME.internal_error_response
handle_unexpected_exception = _APP_HOOKS_RUNTIME.handle_unexpected_exception
_requires_ops_internal_auth = _APP_HOOKS_RUNTIME.requires_ops_internal_auth
require_ops_internal_auth = _APP_HOOKS_RUNTIME.require_ops_internal_auth


_RUNTIME_PATHS = load_runtime_paths(
    environ=os.environ,
    secret_loader=_env_or_secret_file,
    default_config_path=os.path.join(os.path.dirname(__file__), "hosts.json"),
)
# These names are populated from the immutable runtime snapshot below. Keep
# their public types visible to static analyzers that cannot evaluate the
# dynamic namespace publication performed by ``publish_runtime_paths``.
CONFIG_PATH: str
DYNAMIC_CONFIG_PATH: str
OPS_CREDENTIALS_PATH: str
OPS_WINRM_TRUST_PATH: str
POWER_CONFIG_PATH: str
POWER_STATUS_CACHE_SECONDS: float
MYSQL_DSN: Optional[str]
GUACAMOLE_MYSQL_DSN: Optional[str]
OPS_MYSQL_DATABASE: Optional[str]
GUACAMOLE_MYSQL_DATABASE: Optional[str]
MYSQL_HOSTNAME: str
MYSQL_PORT: int
OPS_MYSQL_USER: str
OPS_MYSQL_PASSWORD: str
GUACAMOLE_MYSQL_USER: str
GUACAMOLE_MYSQL_PASSWORD: str
publish_runtime_paths(_RUNTIME_PATHS, globals())


_INPUT_CONTEXT = InputContext(
    coerce_bool=lambda value: _coerce_bool_impl(value),
    parse_bool=lambda value, default: _parse_bool_impl(value, default),
    normalize_args=lambda value, default=None: _normalize_args_impl(value, default),
    parse_recipients=lambda value, default=None: _parse_recipients_impl(value, default),
)
_INPUT_RUNTIME = create_input_runtime(_INPUT_CONTEXT)
_coerce_bool = _INPUT_RUNTIME.coerce_bool
parse_bool = _INPUT_RUNTIME.parse_bool
normalize_args = _INPUT_RUNTIME.normalize_args
parse_recipients = _INPUT_RUNTIME.parse_recipients


_RUNTIME_POLICY = load_runtime_policy(
    environ=os.environ,
    secret_loader=_env_or_secret_file,
    parse_recipients=parse_recipients,
    http_header_pattern=HTTP_HEADER_NAME_RE,
    is_lite=_is_lite_gateway,
    log_error=logging.error,
)
# ``publish_runtime_policy`` preserves the worker's historical module-level
# names, so declare the values used by callers and tests for type checkers.
DEMO_USER: str
DEMO_LAB_ID: str
DEMO_CONNECTION_ID: str
DEMO_HEARTBEAT_MAX_AGE_SECONDS: int
DEMO_OPERATION_ID_RE: Pattern[str]
DEMO_EVENT_ACTIONS: Dict[str, str]
GUACAMOLE_TEMP_USER_CLEANUP_ENABLED: bool
GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS: int
GUACAMOLE_PROVISIONER_TOKEN: str
GUACAMOLE_PROVISIONER_TOKEN_HEADER: str
WINRM_READ_TIMEOUT: int
WINRM_OPERATION_TIMEOUT: int
WINRM_ALLOWED_TRANSPORTS: Set[str]
WINRM_MANAGEMENT_CIDRS: List[str]
ALLOWED_WINRM_COMMANDS: Set[str]
TIMELINE_MAX_LIMIT: int
TIMELINE_DEFAULT_LIMIT: int
TIMELINE_PHASE_LOOKBACK: int
NOTIFICATION_SERVICE_URL: str
NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER: str
NOTIFICATION_SERVICE_ACCESS_TOKEN: str
NOTIFICATION_SERVICE_ENABLED: bool
NOTIFICATION_SERVICE_RETRY_ATTEMPTS: int
NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS: int
NOTIFICATION_SERVICE_RECIPIENTS: List[str]
OPS_ALERT_FAILURE_THRESHOLD: int
OPS_ALERT_WINDOW_SECONDS: int
OPS_ALERT_COOLDOWN_SECONDS: int
ACCESS_AUDIT_URL: str
SESSION_OBSERVER_GATEWAY_ID: str
SESSION_OBSERVER_SIGNING_SECRET: str
SESSION_OBSERVATION_OUTBOX_ENABLED: bool
SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS: int
SESSION_OBSERVATION_OUTBOX_BATCH_SIZE: int
SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS: int
SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS: int
SESSION_OBSERVATION_INGEST_TOKEN: str
OPS_INTERNAL_AUTH_TOKEN: str
OPS_INTERNAL_AUTH_HEADER: str
GUAC_ADMIN_USER: str
GUAC_ADMIN_PASS: str
GUAC_API_URL: str
GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS: int
GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS: int
GUACAMOLE_HISTORY_LOOKBACK_SECONDS: int
GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS: int
HEARTBEAT_SSE_INTERVAL_SECONDS: int
DISCOVERY_TIMEOUT_SECONDS: float
DISCOVERY_LABSTATION_PORTS: List[int]
DISCOVERY_LABSTATION_PATHS: List[str]
DISCOVERY_HEARTBEAT_PATHS: List[str]
publish_runtime_policy(_RUNTIME_POLICY, globals())
# The Ops Worker is intentionally not a public API. OpenResty authenticates
# the operator at the edge and injects this separate, gateway-local credential.
OPS_INTERNAL_AUTH_TOKEN = _RUNTIME_POLICY.ops_internal_auth_token
OPS_INTERNAL_AUTH_HEADER = _RUNTIME_POLICY.ops_internal_auth_header
GUAC_ADMIN_USER = _RUNTIME_POLICY.guac_admin_user
GUAC_ADMIN_PASS = _RUNTIME_POLICY.guac_admin_pass
GUAC_API_URL = _RUNTIME_POLICY.guac_api_url
GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS = _RUNTIME_POLICY.guac_token_revocation_interval_seconds
GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS = _RUNTIME_POLICY.guac_token_revocation_max_attempts
GUACAMOLE_HISTORY_LOOKBACK_SECONDS = _RUNTIME_POLICY.guacamole_history_lookback_seconds
GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS = _RUNTIME_POLICY.guacamole_history_reconciliation_retention_seconds
HEARTBEAT_SSE_INTERVAL_SECONDS = _RUNTIME_POLICY.heartbeat_sse_interval_seconds
DISCOVERY_TIMEOUT_SECONDS = _RUNTIME_POLICY.discovery_timeout_seconds
DISCOVERY_LABSTATION_PORTS = _RUNTIME_POLICY.discovery_labstation_ports
DISCOVERY_LABSTATION_PATHS = _RUNTIME_POLICY.discovery_labstation_paths
DISCOVERY_HEARTBEAT_PATHS = _RUNTIME_POLICY.discovery_heartbeat_paths
_FERNET: Optional[Fernet] = None


def _set_cached_fernet(value: Optional[Fernet]) -> None:
    global _FERNET
    _FERNET = value


APP = create_app(
    __name__,
    internal_error_response=lambda context, exc: internal_error_response(context, exc),
    internal_auth_token=lambda: OPS_INTERNAL_AUTH_TOKEN,
    internal_auth_header=lambda: OPS_INTERNAL_AUTH_HEADER,
    requires_internal_auth=_requires_ops_internal_auth,
)


_CREDENTIAL_CONTEXT = CredentialContext(
    load_fernet_impl=lambda current, **kwargs: _load_fernet_store_impl(
        current,
        **kwargs,
    ),
    get_cached_fernet=lambda: _FERNET,
    set_cached_fernet=_set_cached_fernet,
    get_load_fernet=lambda: _load_fernet,
    get_read_secret=lambda: _env_or_secret_file,
    get_fernet_factory=lambda: Fernet,
    normalize_credential_ref=lambda value: _normalize_credential_ref_impl(value),
    credential_ref_for_host=lambda host, **kwargs: _credential_ref_for_host_impl(
        host,
        **kwargs,
    ),
    read_credentials_store_impl=lambda path: _read_credentials_store_impl(path),
    get_credentials_path=lambda: OPS_CREDENTIALS_PATH,
    write_credentials_store_impl=lambda path, data: _write_credentials_store_impl(
        path,
        data,
    ),
    save_credentials_impl=lambda *args, **kwargs: _save_credentials_store_impl(
        *args,
        **kwargs,
    ),
    load_credentials_impl=lambda *args, **kwargs: _load_credentials_store_impl(
        *args,
        **kwargs,
    ),
    fernet_key_is_usable_impl=lambda **kwargs: _fernet_key_is_usable_impl(**kwargs),
    get_logger=lambda: logging,
)
_CREDENTIAL_RUNTIME = create_credential_runtime(_CREDENTIAL_CONTEXT)
_load_fernet = _CREDENTIAL_RUNTIME.load_fernet
normalize_credential_ref = _CREDENTIAL_RUNTIME.normalize_credential_ref
credential_ref_for_host = _CREDENTIAL_RUNTIME.credential_ref_for_host
read_winrm_credentials_store = _CREDENTIAL_RUNTIME.read_winrm_credentials_store
write_winrm_credentials_store = _CREDENTIAL_RUNTIME.write_winrm_credentials_store
save_winrm_credentials = _CREDENTIAL_RUNTIME.save_winrm_credentials
load_winrm_credentials = _CREDENTIAL_RUNTIME.load_winrm_credentials
winrm_credentials_configured = _CREDENTIAL_RUNTIME.winrm_credentials_configured
fernet_key_is_usable = _CREDENTIAL_RUNTIME.fernet_key_is_usable


WINRM_CERTIFICATE_MAX_BYTES = _WINRM_CERTIFICATE_MAX_BYTES_DEFAULT


_WINRM_TRUST_CONTEXT = WinRMTrustContext(
    normalize_winrm_trust_ref=lambda value: _normalize_trust_ref_impl(
        value,
        secure_filename=secure_filename,
        trust_ref_pattern=WINRM_TRUST_REF_RE,
    ),
    trust_http_status=lambda code: _trust_http_status_impl(code),
    winrm_trust_error_payload=lambda host_name, code: _build_winrm_trust_error_payload_impl(
        host_name,
        code,
        request_id=_request_id,
        trust_error_messages=WINRM_TRUST_ERROR_MESSAGES,
    ),
    winrm_trust_ref_for_host=lambda host: _trust_ref_for_host_impl(
        host,
        normalize_ref=normalize_winrm_trust_ref,
    ),
    winrm_trust_root=lambda: _resolve_trust_root_impl(
        OPS_WINRM_TRUST_PATH,
        realpath=os.path.realpath,
        abspath=os.path.abspath,
        trust_error_type=WinRMTrustError,
        invalid_message=WINRM_CERTIFICATE_INVALID_MESSAGE,
    ),
    winrm_trust_file_path=lambda host, filename: _resolve_trust_file_path_impl(
        host,
        filename,
        root=_winrm_trust_root(),
        trust_ref_for_host=winrm_trust_ref_for_host,
        resolve_path=_resolve_winrm_trust_file_path,
    ),
    winrm_trust_certificate_path=lambda host: _winrm_trust_file_path(
        host,
        WINRM_TRUST_CERTIFICATE_NAME,
    ),
    winrm_trust_pem_path=lambda host: _winrm_trust_file_path(
        host,
        WINRM_TRUST_PEM_NAME,
    ),
    parse_winrm_certificate=lambda path: _read_trust_certificate_impl(
        path,
        max_bytes=WINRM_CERTIFICATE_MAX_BYTES,
        parse_certificate_bytes=_parse_winrm_certificate_bytes,
    ),
    parse_winrm_certificate_bytes=lambda raw: _parse_winrm_certificate_bytes_impl(
        raw,
        max_bytes=WINRM_CERTIFICATE_MAX_BYTES,
    ),
    winrm_trust_metadata_path=lambda host: _winrm_trust_file_path(
        host,
        WINRM_TRUST_METADATA_NAME,
    ),
    write_winrm_trust_bytes=lambda path, content: _write_trust_bytes_impl(
        path,
        content,
    ),
    read_winrm_trust_metadata=lambda host: _read_trust_metadata_file(
        _winrm_trust_metadata_path(host)
    ),
    write_winrm_trust_metadata=lambda host, metadata: _write_trust_metadata_file(
        _winrm_trust_metadata_path(host),
        metadata,
        write_bytes=_write_winrm_trust_bytes,
    ),
    validate_winrm_certificate=lambda certificate, host: _validate_winrm_certificate_impl(
        certificate,
        host,
        winrm_trust_ref_for_host(host),
        certificate_matches_host=_certificate_matches_host,
        certificate_metadata=_winrm_certificate_metadata,
        trust_error_messages=WINRM_TRUST_ERROR_MESSAGES,
        invalid_message=WINRM_CERTIFICATE_INVALID_MESSAGE,
    ),
    read_winrm_certificate_upload=lambda: _read_certificate_upload_impl(
        files=request.files,
        content_length=request.content_length,
        body_reader=lambda: request.get_data(cache=False, as_text=False),
        max_bytes=WINRM_CERTIFICATE_MAX_BYTES,
        allowed_extensions=WINRM_CERTIFICATE_EXTENSIONS,
        secure_filename=secure_filename,
        trust_error_type=WinRMTrustError,
        required_code="WINRM_CERTIFICATE_REQUIRED",
        required_message=WINRM_CERTIFICATE_REQUIRED_MESSAGE,
        invalid_code="WINRM_TRUST_INVALID",
        invalid_message=WINRM_CERTIFICATE_INVALID_MESSAGE,
    ),
    winrm_trust_request_value=lambda name: _trust_request_value_impl(
        name,
        form=request.form,
        is_json=request.is_json,
        json_payload=request.get_json(silent=True) if request.is_json else None,
    ),
    winrm_certificate_response_metadata=lambda certificate, host, input_format: _certificate_response_metadata_impl(
        certificate,
        host,
        input_format,
        trust_ref_for_host=winrm_trust_ref_for_host,
        certificate_metadata=_winrm_certificate_metadata,
    ),
    store_winrm_trust_certificate=lambda host, certificate: _store_trust_certificate_impl(
        host,
        certificate,
        response_metadata=_winrm_certificate_response_metadata,
        write_bytes=_write_winrm_trust_bytes,
        certificate_path_for_host=winrm_trust_certificate_path,
        write_metadata=_write_winrm_trust_metadata,
        materialize_pem=_materialize_winrm_pem,
        inspect_trust=inspect_winrm_trust,
        format_datetime=_format_certificate_datetime,
        now=lambda: datetime.now(timezone.utc),
    ),
    delete_winrm_trust_certificate=lambda host: _delete_trust_certificate_impl(
        host,
        file_path_for_host=_winrm_trust_file_path,
        certificate_name=WINRM_TRUST_CERTIFICATE_NAME,
        pem_name=WINRM_TRUST_PEM_NAME,
        metadata_name=WINRM_TRUST_METADATA_NAME,
        delete_files=_delete_trust_files_impl,
    ),
    materialize_winrm_pem=lambda host, certificate: _materialize_trust_pem_impl(
        winrm_trust_pem_path(host),
        certificate,
        max_bytes=WINRM_CERTIFICATE_MAX_BYTES,
    ),
    inspect_winrm_trust=lambda host: _inspect_winrm_trust_impl(
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
    ),
    load_winrm_trust=lambda host: _load_winrm_trust_impl(
        host,
        inspect_trust=inspect_winrm_trust,
        pem_path_for_host=winrm_trust_pem_path,
        required_code=WINRM_TRUST_REQUIRED_CODE,
        required_message=WINRM_TRUST_REQUIRED_MESSAGE,
        expired_message=WINRM_CERTIFICATE_EXPIRED_MESSAGE,
        not_yet_valid_message=WINRM_CERTIFICATE_NOT_YET_VALID_MESSAGE,
        trust_error_messages=WINRM_TRUST_ERROR_MESSAGES,
        invalid_message=WINRM_CERTIFICATE_INVALID_MESSAGE,
    ),
    refresh_winrm_trust_store=lambda hosts: _refresh_winrm_trust_store_impl(
        hosts,
        _winrm_trust_root(),
        trust_ref_for_host=winrm_trust_ref_for_host,
        inspect_trust=inspect_winrm_trust,
        sanitize_log_value=_sanitize_log_value,
        logger=logging,
    ),
)
_WINRM_TRUST_RUNTIME = create_winrm_trust_runtime(_WINRM_TRUST_CONTEXT)
_winrm_trust_http_status = _WINRM_TRUST_RUNTIME.trust_http_status
_winrm_trust_error_payload = _WINRM_TRUST_RUNTIME.winrm_trust_error_payload
normalize_winrm_trust_ref = _WINRM_TRUST_RUNTIME.normalize_winrm_trust_ref
winrm_trust_ref_for_host = _WINRM_TRUST_RUNTIME.winrm_trust_ref_for_host
_winrm_trust_root = _WINRM_TRUST_RUNTIME.winrm_trust_root
_winrm_trust_file_path = _WINRM_TRUST_RUNTIME.winrm_trust_file_path
winrm_trust_certificate_path = _WINRM_TRUST_RUNTIME.winrm_trust_certificate_path
winrm_trust_pem_path = _WINRM_TRUST_RUNTIME.winrm_trust_pem_path
_parse_winrm_certificate = _WINRM_TRUST_RUNTIME.parse_winrm_certificate
_parse_winrm_certificate_bytes = _WINRM_TRUST_RUNTIME.parse_winrm_certificate_bytes
_winrm_trust_metadata_path = _WINRM_TRUST_RUNTIME.winrm_trust_metadata_path
_write_winrm_trust_bytes = _WINRM_TRUST_RUNTIME.write_winrm_trust_bytes
_read_winrm_trust_metadata = _WINRM_TRUST_RUNTIME.read_winrm_trust_metadata
_write_winrm_trust_metadata = _WINRM_TRUST_RUNTIME.write_winrm_trust_metadata
_validate_winrm_certificate = _WINRM_TRUST_RUNTIME.validate_winrm_certificate
_read_winrm_certificate_upload = _WINRM_TRUST_RUNTIME.read_winrm_certificate_upload
_winrm_trust_request_value = _WINRM_TRUST_RUNTIME.winrm_trust_request_value
_winrm_certificate_response_metadata = _WINRM_TRUST_RUNTIME.winrm_certificate_response_metadata
_store_winrm_trust_certificate = _WINRM_TRUST_RUNTIME.store_winrm_trust_certificate
_delete_winrm_trust_certificate = _WINRM_TRUST_RUNTIME.delete_winrm_trust_certificate
_materialize_winrm_pem = _WINRM_TRUST_RUNTIME.materialize_winrm_pem
inspect_winrm_trust = _WINRM_TRUST_RUNTIME.inspect_winrm_trust
load_winrm_trust = _WINRM_TRUST_RUNTIME.load_winrm_trust
refresh_winrm_trust_store = _WINRM_TRUST_RUNTIME.refresh_winrm_trust_store


_HOST_CONFIG_CONTEXT = HostConfigContext(
    read_hosts_config_impl=lambda path, missing_ok=True: _read_hosts_config_impl(
        path,
        missing_ok,
    ),
    merge_host_configs_impl=lambda base, dynamic: _merge_host_configs_impl(base, dynamic),
    resolve_host_secret_refs_impl=lambda raw, **kwargs: _resolve_host_secret_refs_impl(
        raw,
        **kwargs,
    ),
    get_credential_ref_for_host=lambda: credential_ref_for_host,
    get_credentials_configured=lambda: winrm_credentials_configured,
    get_logger=lambda: logging,
    catalog_bool_impl=lambda value: _catalog_bool_impl(value),
    resolve_addresses_impl=lambda address, **kwargs: _resolve_addresses_impl(
        address,
        **kwargs,
    ),
    get_ip_address=lambda: ipaddress.ip_address,
    get_getaddrinfo=lambda: socket.getaddrinfo,
    validate_winrm_catalog_impl=lambda config, **kwargs: _validate_winrm_catalog_impl(
        config,
        **kwargs,
    ),
    get_management_cidrs=lambda: WINRM_MANAGEMENT_CIDRS,
    get_winrm_port=lambda: WINRM_PORT,
    get_trust_ref_pattern=lambda: WINRM_TRUST_REF_RE,
    get_catalog_bool=lambda: _catalog_bool,
    get_resolved_addresses=lambda: _resolved_addresses,
    load_host_config_impl=lambda *args, **kwargs: _load_host_config_impl(*args, **kwargs),
    get_config_path=lambda: CONFIG_PATH,
    get_dynamic_config_path=lambda: DYNAMIC_CONFIG_PATH,
    get_read_hosts_config=lambda: read_hosts_config,
    get_merge_host_configs=lambda: merge_host_configs,
    get_validate_winrm_catalog=lambda: validate_winrm_catalog,
    get_resolve_host_secret_refs=lambda: resolve_host_secret_refs,
    build_ops_dsn_impl=lambda *args, **kwargs: _build_ops_dsn_impl(*args, **kwargs),
    get_mysql_dsn=lambda: MYSQL_DSN,
    get_ops_mysql_user=lambda: OPS_MYSQL_USER,
    get_ops_mysql_password=lambda: OPS_MYSQL_PASSWORD,
    get_ops_mysql_database=lambda: OPS_MYSQL_DATABASE,
    get_mysql_hostname=lambda: MYSQL_HOSTNAME,
    get_mysql_port=lambda: MYSQL_PORT,
    get_url_create=lambda: URL.create,
    build_guacamole_dsn_impl=lambda *args, **kwargs: _build_guacamole_dsn_impl(
        *args,
        **kwargs,
    ),
    get_guacamole_dsn=lambda: GUACAMOLE_MYSQL_DSN,
    get_guacamole_user=lambda: GUACAMOLE_MYSQL_USER,
    get_guacamole_password=lambda: GUACAMOLE_MYSQL_PASSWORD,
    get_guacamole_database=lambda: GUACAMOLE_MYSQL_DATABASE,
    get_parse_url=lambda: make_url,
    get_load_dynamic_config=lambda: load_dynamic_config,
    get_write_dynamic_config=lambda: write_dynamic_config,
    load_dynamic_config_impl=lambda *args, **kwargs: _load_dynamic_config_impl(
        *args,
        **kwargs,
    ),
    write_dynamic_config_impl=lambda *args, **kwargs: _write_dynamic_config_impl(
        *args,
        **kwargs,
    ),
    get_path_dirname=lambda: os.path.dirname,
    get_make_dirs=lambda: os.makedirs,
    get_open_file=lambda: open,
    get_dump_json=lambda: json.dump,
    get_replace_file=lambda: os.replace,
    upsert_dynamic_host_impl=lambda *args, **kwargs: _upsert_dynamic_host_impl(
        *args,
        **kwargs,
    ),
    get_normalize_match_key=lambda: normalize_match_key,
    get_sanitize_host_name=lambda: sanitize_host_name,
    get_normalize_mac=lambda: normalize_mac,
    get_host_get=lambda: HOSTS.get,
    update_dynamic_host_impl=lambda *args, **kwargs: _update_dynamic_host_impl(
        *args,
        **kwargs,
    ),
)
_HOST_CONFIG_RUNTIME = create_host_config_runtime(_HOST_CONFIG_CONTEXT)
read_hosts_config = _HOST_CONFIG_RUNTIME.read_hosts_config
merge_host_configs = _HOST_CONFIG_RUNTIME.merge_host_configs
resolve_host_secret_refs = _HOST_CONFIG_RUNTIME.resolve_host_secret_refs
_catalog_bool = _HOST_CONFIG_RUNTIME.catalog_bool
_resolved_addresses = _HOST_CONFIG_RUNTIME.resolved_addresses
validate_winrm_catalog = _HOST_CONFIG_RUNTIME.validate_winrm_catalog
load_config = _HOST_CONFIG_RUNTIME.load_config
build_ops_dsn = _HOST_CONFIG_RUNTIME.build_ops_dsn
build_guacamole_dsn = _HOST_CONFIG_RUNTIME.build_guacamole_dsn
load_dynamic_config = _HOST_CONFIG_RUNTIME.load_dynamic_config
write_dynamic_config = _HOST_CONFIG_RUNTIME.write_dynamic_config
upsert_dynamic_host = _HOST_CONFIG_RUNTIME.upsert_dynamic_host
update_dynamic_host = _HOST_CONFIG_RUNTIME.update_dynamic_host


_RUNTIME_STATE = create_runtime_state(
    load_hosts=load_config,
    registry_factory=HostRegistry,
    build_ops_dsn=build_ops_dsn,
    build_guacamole_dsn=build_guacamole_dsn,
    create_engine=create_engine,
)
HOSTS = _RUNTIME_STATE.hosts
HOSTS_LOCK = _RUNTIME_STATE.hosts_lock
OPS_DSN = _RUNTIME_STATE.ops_dsn
DB_ENGINE: Optional[Engine] = _RUNTIME_STATE.db_engine
GUACAMOLE_DSN = _RUNTIME_STATE.guacamole_dsn
GUACAMOLE_DB_ENGINE: Optional[Engine] = _RUNTIME_STATE.guacamole_db_engine


_HEARTBEAT_CONTEXT = HeartbeatContext(
    parse_datetime=lambda value: datetime.fromisoformat(value),
    utc_timezone=timezone.utc,
    now=lambda: datetime.now(timezone.utc),
    sql_text=text,
    json_dumps=json.dumps,
    read_remote_file=lambda *args, **kwargs: read_remote_file(*args, **kwargs),
    get_db_engine=lambda: DB_ENGINE,
    sync_lab_to_basyx=lambda *args, **kwargs: aas_generator.sync_lab_to_basyx(
        *args,
        **kwargs,
    ),
    resolve_lab_ids_for_host=lambda host: resolve_lab_ids_for_host(host),
    get_logger=lambda: logging,
    get_host_registry=lambda: HOSTS,
    get_persist_heartbeat=lambda *args, **kwargs: persist_heartbeat(*args, **kwargs),
    get_poll_heartbeat=lambda *args, **kwargs: poll_heartbeat(*args, **kwargs),
    fetch_latest_heartbeat=lambda *args, **kwargs: _fetch_latest_heartbeat(
        *args,
        **kwargs,
    ),
    trust_error_type=WinRMTrustError,
    missing_credentials_predicate=lambda error: is_missing_winrm_credentials_error(error),
    trust_error_payload=lambda host_name, code: _winrm_trust_error_payload(host_name, code),
    request_id=lambda: _request_id(),
    sanitize_log_value=lambda value: _sanitize_log_value(value),
    credentials_required_message=WINRM_CREDENTIALS_REQUIRED_MESSAGE,
    heartbeat_interval_seconds=HEARTBEAT_SSE_INTERVAL_SECONDS,
    sleep=lambda seconds: time.sleep(seconds),
)
_HEARTBEAT_RUNTIME = create_heartbeat_runtime(_HEARTBEAT_CONTEXT)
to_utc = _HEARTBEAT_RUNTIME.to_utc


_WINRM_CONTEXT = WinRMContext(
    get_winrm_port=lambda: WINRM_PORT,
    get_allowed_transports=lambda: WINRM_ALLOWED_TRANSPORTS,
    coerce_bool=lambda value: _coerce_bool(value),
    get_credential_ref_for_host=lambda host: credential_ref_for_host(host),
    get_load_credentials=lambda reference: load_winrm_credentials(reference),
    get_credentials_required_message=lambda: WINRM_CREDENTIALS_REQUIRED_MESSAGE,
    get_load_trust=lambda host: load_winrm_trust(host),
    get_session_factory=lambda: lambda *args, **kwargs: winrm.Session(*args, **kwargs),
    get_ssl_error_type=lambda: requests.exceptions.SSLError,
    get_trust_error_type=lambda: WinRMTrustError,
    tls_error_code="WINRM_TLS_FAILED",
    tls_error_message=WINRM_TLS_FAILED_MESSAGE,
    get_default_executable=lambda: DEFAULT_LABSTATION_EXE,
    get_read_timeout_sec=lambda: WINRM_READ_TIMEOUT,
    get_operation_timeout_sec=lambda: WINRM_OPERATION_TIMEOUT,
    get_logger=lambda: logging,
    clock=lambda: time.time(),
    get_resolve_credentials=lambda: _winrm_credentials,
    get_resolve_policy=lambda: _winrm_connection_policy,
    get_create_session=lambda: create_winrm_session,
    get_run_method=lambda: run_winrm_method,
    get_build_labstation_command=lambda: _build_labstation_command_impl,
    get_build_read_remote_file_command=lambda: _build_read_remote_file_command_impl,
    get_build_write_remote_file_command=lambda: _build_write_remote_file_command_impl,
    get_build_remove_remote_file_command=lambda: _build_remove_remote_file_command_impl,
)
_WINRM_RUNTIME = create_winrm_runtime(_WINRM_CONTEXT)
_winrm_connection_policy = _WINRM_RUNTIME.winrm_connection_policy
_winrm_credentials = _WINRM_RUNTIME.winrm_credentials
create_winrm_session = _WINRM_RUNTIME.create_winrm_session
run_winrm_method = _WINRM_RUNTIME.run_winrm_method
winrm_endpoint = _WINRM_RUNTIME.winrm_endpoint
run_labstation_command = _WINRM_RUNTIME.run_labstation_command
run_remote_powershell = _WINRM_RUNTIME.run_remote_powershell
read_remote_file = _WINRM_RUNTIME.read_remote_file
write_remote_file = _WINRM_RUNTIME.write_remote_file
remove_remote_file = _WINRM_RUNTIME.remove_remote_file


get_local_mode_flag_path = _get_local_mode_flag_path_impl


persist_heartbeat = _HEARTBEAT_RUNTIME.persist_heartbeat


_DATABASE_CONTEXT = DatabaseContext(
    database_is_usable=lambda engine, statement, **kwargs: _database_is_usable_impl(
        engine,
        statement,
        **kwargs,
    ),
    get_sql_text=lambda: text,
    get_logger=lambda: logging,
)
_DATABASE_RUNTIME = create_database_runtime(_DATABASE_CONTEXT)
database_is_usable = _DATABASE_RUNTIME.database_is_usable

_RESERVATION_EXECUTION_CONTEXT = ReservationExecutionContext(
    record_reservation_operation_impl=lambda *args, **kwargs: _record_reservation_operation_impl(
        *args,
        **kwargs,
    ),
    get_db_engine=lambda: DB_ENGINE,
    get_now_utc=lambda: _now_utc,
    get_sql_text=lambda: text,
    get_json_dumps=lambda: json.dumps,
    get_check_failure_alert=lambda: _check_failure_alert,
    check_failure_alert_impl=lambda *args, **kwargs: _check_failure_alert_impl(
        *args,
        **kwargs,
    ),
    get_logger=lambda: logging,
    get_sanitize_log_value=lambda: _sanitize_log_value,
    project_power_operation_impl=lambda *args, **kwargs: _project_power_operation_impl(
        *args,
        **kwargs,
    ),
    get_record_reservation_operation=lambda: record_reservation_operation,
    host_local_mode_enabled_impl=lambda *args, **kwargs: _host_local_mode_enabled_impl(
        *args,
        **kwargs,
    ),
    get_fetch_latest_heartbeat=lambda: _fetch_latest_heartbeat,
    get_parse_bool=lambda: parse_bool,
    execute_reservation_power_phase_impl=lambda *args, **kwargs: _execute_reservation_power_phase_impl(
        *args,
        **kwargs,
    ),
    get_power_runtime=lambda: POWER_RUNTIME,
    get_power_validation_error_type=lambda: PowerValidationError,
    get_host_local_mode_enabled=lambda: _host_local_mode_enabled,
    should_send_failure_alert_impl=lambda *args, **kwargs: _should_send_failure_alert_impl(
        *args,
        **kwargs,
    ),
    get_notification_enabled=lambda: NOTIFICATION_SERVICE_ENABLED,
    get_notification_url=lambda: NOTIFICATION_SERVICE_URL,
    get_failure_threshold=lambda: OPS_ALERT_FAILURE_THRESHOLD,
    get_window_seconds=lambda: OPS_ALERT_WINDOW_SECONDS,
    get_cooldown_seconds=lambda: OPS_ALERT_COOLDOWN_SECONDS,
    get_should_send_failure_alert=lambda: _should_send_failure_alert,
    send_failure_alert_impl=lambda *args, **kwargs: _send_failure_alert_impl(
        *args,
        **kwargs,
    ),
    get_send_failure_alert=lambda: _send_failure_alert,
    get_recipients=lambda: NOTIFICATION_SERVICE_RECIPIENTS,
    get_token_header=lambda: NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER,
    get_token=lambda: NOTIFICATION_SERVICE_ACCESS_TOKEN,
    get_retry_attempts=lambda: NOTIFICATION_SERVICE_RETRY_ATTEMPTS,
    get_retry_backoff_seconds=lambda: NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS,
    get_http_post=lambda: requests.post,
    get_sleep=lambda: time.sleep,
    get_current_epoch=lambda: time.time,
    notify_critical_failure_impl=lambda *args, **kwargs: _notify_critical_failure_impl(
        *args,
        **kwargs,
    ),
    get_notify_critical_failure=lambda: notify_critical_failure,
    perform_wake_step_impl=lambda *args, **kwargs: _perform_wake_step_impl(
        *args,
        **kwargs,
    ),
    get_wol_and_wait=lambda: wol_and_wait,
    get_run_labstation_command=lambda: run_labstation_command,
    perform_command_step_impl=lambda *args, **kwargs: _perform_command_step_impl(
        *args,
        **kwargs,
    ),
)
_RESERVATION_EXECUTION_RUNTIME = create_reservation_execution_runtime(
    _RESERVATION_EXECUTION_CONTEXT
)
record_reservation_operation = _RESERVATION_EXECUTION_RUNTIME.record_reservation_operation
_record_power_operation = _RESERVATION_EXECUTION_RUNTIME.record_power_operation
_host_local_mode_enabled = _RESERVATION_EXECUTION_RUNTIME.host_local_mode_enabled
_execute_reservation_power_phase = _RESERVATION_EXECUTION_RUNTIME.execute_reservation_power_phase
_should_send_failure_alert = _RESERVATION_EXECUTION_RUNTIME.should_send_failure_alert
_send_failure_alert = _RESERVATION_EXECUTION_RUNTIME.send_failure_alert
_check_failure_alert = _RESERVATION_EXECUTION_RUNTIME.check_failure_alert
notify_critical_failure = _RESERVATION_EXECUTION_RUNTIME.notify_critical_failure
perform_wake_step = _RESERVATION_EXECUTION_RUNTIME.perform_wake_step
perform_command_step = _RESERVATION_EXECUTION_RUNTIME.perform_command_step
poll_heartbeat = _HEARTBEAT_RUNTIME.poll_heartbeat

_format_sse_event = _HEARTBEAT_RUNTIME.format_sse_event


generate_heartbeat_stream = _HEARTBEAT_RUNTIME.generate_heartbeat_stream



_DEMO_CONTEXT = DemoContext(
    get_mandatory_field_impl=lambda payload, *keys: _get_mandatory_field_impl(
        payload,
        *keys,
    ),
    canonical_demo_lab_id_impl=lambda value: _canonical_demo_lab_id_impl(value),
    build_demo_readiness_impl=lambda *args, **kwargs: _build_demo_readiness_impl(
        *args,
        **kwargs,
    ),
    get_demo_lab_id=lambda: DEMO_LAB_ID,
    get_demo_connection_id=lambda: DEMO_CONNECTION_ID,
    get_demo_user=lambda: DEMO_USER,
    get_demo_heartbeat_max_age=lambda: DEMO_HEARTBEAT_MAX_AGE_SECONDS,
    get_guacamole_db_engine=lambda: GUACAMOLE_DB_ENGINE,
    get_db_engine=lambda: DB_ENGINE,
    get_find_host_by_lab=lambda: resolve_host_by_lab,
    get_fetch_latest_heartbeat=lambda: _fetch_latest_heartbeat,
    get_to_utc=lambda: to_utc,
    get_sql_text=lambda: text,
    get_now=lambda: lambda: datetime.now(timezone.utc),
    get_logger=lambda: logging,
    build_demo_context_impl=lambda *args, **kwargs: _build_demo_context_impl(
        *args,
        **kwargs,
    ),
    get_demo_operation_id_pattern=lambda: DEMO_OPERATION_ID_RE,
    get_canonical_demo_lab_id=lambda: _canonical_demo_lab_id,
    operation_completed_impl=lambda *args, **kwargs: _demo_operation_completed_impl(
        *args,
        **kwargs,
    ),
    record_demo_event_impl=lambda *args, **kwargs: _record_demo_event_impl(
        *args,
        **kwargs,
    ),
    get_demo_event_actions=lambda: DEMO_EVENT_ACTIONS,
    get_record_reservation_operation=lambda: record_reservation_operation,
    demo_host_is_ready_impl=lambda *args, **kwargs: _demo_host_is_ready_impl(
        *args,
        **kwargs,
    ),
    handle_demo_start_impl=lambda *args, **kwargs: _handle_demo_start_impl(
        *args,
        **kwargs,
    ),
    get_demo_context=lambda: _demo_context,
    get_operation_completed=lambda: _demo_operation_completed,
    get_parse_bool=lambda: parse_bool,
    get_demo_host_is_ready=lambda: _demo_host_is_ready,
    get_reservation_start=lambda: handle_reservation_start,
    get_reservation_end=lambda: handle_reservation_end,
    get_record_demo_event=lambda: _record_demo_event,
    handle_demo_event_impl=lambda *args, **kwargs: _handle_demo_event_impl(
        *args,
        **kwargs,
    ),
    handle_demo_end_impl=lambda *args, **kwargs: _handle_demo_end_impl(
        *args,
        **kwargs,
    ),
)
_DEMO_RUNTIME = create_demo_runtime(_DEMO_CONTEXT)
_get_mandatory_field = _DEMO_RUNTIME.get_mandatory_field
_canonical_demo_lab_id = _DEMO_RUNTIME.canonical_demo_lab_id
demo_readiness = _DEMO_RUNTIME.demo_readiness
_demo_context = _DEMO_RUNTIME.demo_context
_demo_operation_completed = _DEMO_RUNTIME.operation_completed
_record_demo_event = _DEMO_RUNTIME.record_demo_event
_demo_host_is_ready = _DEMO_RUNTIME.host_is_ready
handle_demo_start = _DEMO_RUNTIME.handle_demo_start
handle_demo_event = _DEMO_RUNTIME.handle_demo_event
handle_demo_end = _DEMO_RUNTIME.handle_demo_end


_RESERVATION_LIFECYCLE_CONTEXT = ReservationLifecycleContext(
    handle_reservation_start_impl=lambda *args, **kwargs: _handle_reservation_start_impl(
        *args,
        **kwargs,
    ),
    handle_reservation_end_impl=lambda *args, **kwargs: _handle_reservation_end_impl(
        *args,
        **kwargs,
    ),
    get_hosts=lambda: HOSTS,
    get_resolve_host_by_lab=lambda: resolve_host_by_lab,
    get_mandatory_field=lambda: _get_mandatory_field,
    get_parse_bool=lambda: parse_bool,
    get_execute_power_phase=lambda: _execute_reservation_power_phase,
    get_perform_wake_step=lambda: perform_wake_step,
    get_perform_command_step=lambda: perform_command_step,
    get_normalize_args=lambda: normalize_args,
)
_RESERVATION_LIFECYCLE_RUNTIME = create_reservation_lifecycle_runtime(
    _RESERVATION_LIFECYCLE_CONTEXT
)
handle_reservation_start = _RESERVATION_LIFECYCLE_RUNTIME.handle_reservation_start
handle_reservation_end = _RESERVATION_LIFECYCLE_RUNTIME.handle_reservation_end


_TIMELINE_CONTEXT = TimelineContext(
    to_iso_impl=lambda value, **kwargs: _to_iso_impl(value, **kwargs),
    get_datetime=lambda: datetime,
    get_timezone=lambda: timezone,
    sanitize_limit_impl=lambda value, **kwargs: _sanitize_limit_impl(value, **kwargs),
    get_default_limit=lambda: TIMELINE_DEFAULT_LIMIT,
    get_max_limit=lambda: TIMELINE_MAX_LIMIT,
    sanitize_offset_impl=lambda value: _sanitize_offset_impl(value),
    rows_to_operations_impl=lambda rows, **kwargs: _rows_to_operations_impl(rows, **kwargs),
    get_to_iso=lambda: _to_iso,
    build_reservation_timeline_impl=lambda *args, **kwargs: _build_reservation_timeline_impl(
        *args,
        **kwargs,
    ),
    get_db_engine=lambda: DB_ENGINE,
    get_host_by_lab=lambda: resolve_host_by_lab,
    get_sql_text=lambda: text,
    get_rows_to_operations=lambda: _rows_to_operations,
    get_phase_lookback=lambda: TIMELINE_PHASE_LOOKBACK,
    get_fetch_latest_heartbeat=lambda: _fetch_latest_heartbeat,
    get_summarize_phases=lambda: _summarize_phases,
    fetch_latest_heartbeat_impl=lambda *args, **kwargs: _fetch_latest_heartbeat_impl(
        *args,
        **kwargs,
    ),
    get_json_loads=lambda: json.loads,
    summarize_phases_impl=lambda operations: _summarize_phases_impl(operations),
)
_TIMELINE_RUNTIME = create_timeline_runtime(_TIMELINE_CONTEXT)
_to_iso = _TIMELINE_RUNTIME.to_iso
_sanitize_limit = _TIMELINE_RUNTIME.sanitize_limit
_sanitize_offset = _TIMELINE_RUNTIME.sanitize_offset
_rows_to_operations = _TIMELINE_RUNTIME.rows_to_operations
build_reservation_timeline = _TIMELINE_RUNTIME.build_reservation_timeline
_fetch_latest_heartbeat = _TIMELINE_RUNTIME.fetch_latest_heartbeat
_summarize_phases = _TIMELINE_RUNTIME.summarize_phases

_HOST_DISCOVERY_CONTEXT = HostDiscoveryContext(
    is_valid_ping_target_impl=lambda target: _is_valid_ping_target_impl(target),
    get_is_valid_ping_target=lambda: _is_valid_ping_target,
    host_is_up_impl=lambda *args, **kwargs: _host_is_up_impl(*args, **kwargs),
    get_winrm_port=lambda: WINRM_PORT,
    get_create_connection=lambda: socket.create_connection,
    get_logger=lambda: logging,
    normalize_match_key_impl=lambda value: _normalize_match_key_impl(value),
    tcp_port_open_impl=lambda *args, **kwargs: _tcp_port_open_impl(*args, **kwargs),
    get_discovery_timeout=lambda: DISCOVERY_TIMEOUT_SECONDS,
    response_looks_like_labstation_impl=lambda response: _response_looks_like_labstation_impl(
        response
    ),
    normalize_mac_impl=lambda value, **kwargs: _normalize_mac_impl(value, **kwargs),
    get_mac_pattern=lambda: MAC_RE,
    parse_boolish_impl=lambda value: _parse_boolish_impl(value),
    extract_nic_candidates_impl=lambda *args, **kwargs: _extract_nic_candidates_from_heartbeat_impl(
        *args,
        **kwargs,
    ),
    get_normalize_mac=lambda: normalize_mac,
    get_parse_boolish=lambda: parse_boolish,
    choose_wol_mac_impl=lambda candidates: _choose_wol_mac_impl(candidates),
    suggest_mac_from_heartbeat_impl=lambda *args, **kwargs: _suggest_mac_from_heartbeat_impl(
        *args,
        **kwargs,
    ),
    get_discovery_ports=lambda: DISCOVERY_LABSTATION_PORTS,
    get_discovery_paths=lambda: DISCOVERY_LABSTATION_PATHS,
    get_http_get=lambda: requests.get,
    get_request_exception=lambda: requests.RequestException,
    get_response_classifier=lambda: response_looks_like_labstation,
    get_suggest_mac=lambda: suggest_mac_from_heartbeat,
    probe_labstation_http_impl=lambda *args, **kwargs: _probe_labstation_http_impl(
        *args,
        **kwargs,
    ),
    query_labstation_task_heartbeat_path_impl=lambda *args, **kwargs: _query_labstation_task_heartbeat_path_impl(
        *args,
        **kwargs,
    ),
    get_run_remote_powershell=lambda: run_remote_powershell,
    get_json_loads=lambda: json.loads,
    build_heartbeat_path_candidates_impl=lambda *args, **kwargs: _build_heartbeat_path_candidates_impl(
        *args,
        **kwargs,
    ),
    get_query_task_path=lambda: query_labstation_task_heartbeat_path,
    get_heartbeat_paths=lambda: DISCOVERY_HEARTBEAT_PATHS,
    discover_heartbeat_hint_impl=lambda *args, **kwargs: _discover_heartbeat_hint_impl(
        *args,
        **kwargs,
    ),
    get_credentials_configured=lambda: winrm_credentials_configured,
    get_path_candidates=lambda: build_heartbeat_path_candidates,
    get_read_remote_file=lambda: read_remote_file,
    get_suggested_mac=lambda: suggest_mac_from_heartbeat,
    guacamole_name_candidates_impl=lambda *args, **kwargs: _guacamole_name_candidates_impl(
        *args,
        **kwargs,
    ),
    get_load_guacamole_connections=lambda: load_guacamole_connections,
    get_normalize_match_key=lambda: normalize_match_key,
    resolve_guacamole_connection_impl=lambda *args, **kwargs: _resolve_guacamole_connection_impl(
        *args,
        **kwargs,
    ),
    discover_labstation_candidate_impl=lambda *args, **kwargs: _discover_labstation_candidate_impl(
        *args,
        **kwargs,
    ),
    get_resolve_dns=lambda: socket.getaddrinfo,
    get_tcp_probe=lambda: tcp_port_open,
    get_http_probe=lambda: probe_labstation_http,
    get_heartbeat_hint=lambda: discover_heartbeat_hint,
    get_name_candidates=lambda: guacamole_name_candidates,
    get_events_path=lambda: r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
)
_HOST_DISCOVERY_RUNTIME = create_host_discovery_runtime(_HOST_DISCOVERY_CONTEXT)
_is_valid_ping_target = _HOST_DISCOVERY_RUNTIME.is_valid_ping_target
host_is_up = _HOST_DISCOVERY_RUNTIME.host_is_up
normalize_match_key = _HOST_DISCOVERY_RUNTIME.normalize_match_key
tcp_port_open = _HOST_DISCOVERY_RUNTIME.tcp_port_open
response_looks_like_labstation = _HOST_DISCOVERY_RUNTIME.response_looks_like_labstation
normalize_mac = _HOST_DISCOVERY_RUNTIME.normalize_mac
parse_boolish = _HOST_DISCOVERY_RUNTIME.parse_boolish
extract_nic_candidates_from_heartbeat = _HOST_DISCOVERY_RUNTIME.extract_nic_candidates_from_heartbeat
choose_wol_mac = _HOST_DISCOVERY_RUNTIME.choose_wol_mac
suggest_mac_from_heartbeat = _HOST_DISCOVERY_RUNTIME.suggest_mac_from_heartbeat
probe_labstation_http = _HOST_DISCOVERY_RUNTIME.probe_labstation_http
query_labstation_task_heartbeat_path = _HOST_DISCOVERY_RUNTIME.query_labstation_task_heartbeat_path
build_heartbeat_path_candidates = _HOST_DISCOVERY_RUNTIME.build_heartbeat_path_candidates
discover_heartbeat_hint = _HOST_DISCOVERY_RUNTIME.discover_heartbeat_hint
guacamole_name_candidates = _HOST_DISCOVERY_RUNTIME.guacamole_name_candidates
resolve_guacamole_connection = _HOST_DISCOVERY_RUNTIME.resolve_guacamole_connection
discover_labstation_candidate = _HOST_DISCOVERY_RUNTIME.discover_labstation_candidate

_WOL_CONTEXT = WolContext(
    wol_and_wait=lambda *args, **kwargs: _wol_and_wait_impl(*args, **kwargs),
    get_send_magic_packet=lambda: wake,
    get_sleep=lambda: time.sleep,
    get_host_is_up=lambda: host_is_up,
)
_WOL_RUNTIME = create_wol_runtime(_WOL_CONTEXT)
wol_and_wait = _WOL_RUNTIME.wol_and_wait


_HOST_PROVISIONING_CONTEXT = HostProvisioningContext(
    get_name_pattern=lambda: HOST_NAME_RE,
    normalize_mac=lambda value: normalize_mac(value),
    normalize_trust_ref=lambda value: normalize_winrm_trust_ref(value),
    get_sanitize_host_name=lambda value, fallback: sanitize_host_name(value, fallback),
)
_HOST_PROVISIONING_RUNTIME = create_host_provisioning_runtime(_HOST_PROVISIONING_CONTEXT)
sanitize_host_name = _HOST_PROVISIONING_RUNTIME.sanitize_host_name
build_provisioned_host = _HOST_PROVISIONING_RUNTIME.build_provisioned_host

_HOST_INVENTORY_CONTEXT = HostInventoryContext(
    get_host_registry=lambda: HOSTS,
    get_hosts_lock=lambda: HOSTS_LOCK,
    load_dynamic_config=lambda: load_dynamic_config(),
    load_guacamole_connections=lambda: load_guacamole_connections(),
    normalize_match_key=lambda value: normalize_match_key(value),
    credential_ref_for_host=lambda host: credential_ref_for_host(host),
    inspect_winrm_trust=lambda host: inspect_winrm_trust(host),
    winrm_credentials_configured=lambda credential_ref: winrm_credentials_configured(
        credential_ref
    ),
)
_HOST_INVENTORY_RUNTIME = create_host_inventory_runtime(_HOST_INVENTORY_CONTEXT)
safe_host_inventory_entry = _HOST_INVENTORY_RUNTIME.safe_host_inventory_entry

_GUACAMOLE_CONTEXT = GuacamoleContext(
    get_load_connections_impl=lambda: _load_guacamole_connections_impl,
    get_db_engine=lambda: GUACAMOLE_DB_ENGINE,
    get_sql_text=lambda: text,
    get_logger=lambda: logging,
    get_request_headers=lambda: request.headers,
    get_check_auth_impl=lambda: _check_guacamole_provisioner_auth_impl,
    get_expected_token=lambda: GUACAMOLE_PROVISIONER_TOKEN,
    get_token_header=lambda: GUACAMOLE_PROVISIONER_TOKEN_HEADER,
    get_jsonify=lambda: jsonify,
    get_parse_selector_impl=lambda: _parse_guacamole_selector_impl,
    get_selector_pattern=lambda: GUAC_SELECTOR_RE,
    get_safe_connection_response_impl=lambda: _safe_connection_response_impl,
    get_provision_impl=lambda: _provision_guacamole_user_impl,
    get_parse_selector=lambda: parse_guacamole_selector,
    get_resolve_connection=lambda: resolve_guacamole_connection,
    get_safe_connection_response=lambda: safe_connection_response,
    get_datetime=lambda: datetime,
    get_timezone=lambda: timezone,
    get_delete_impl=lambda: _delete_guacamole_user_impl,
    get_cleanup_impl=lambda: _cleanup_guacamole_users_impl,
)
_GUACAMOLE_RUNTIME = create_guacamole_runtime(_GUACAMOLE_CONTEXT)
load_guacamole_connections = _GUACAMOLE_RUNTIME.load_guacamole_connections
require_guacamole_provisioner_auth = _GUACAMOLE_RUNTIME.require_guacamole_provisioner_auth
parse_guacamole_selector = _GUACAMOLE_RUNTIME.parse_guacamole_selector
safe_connection_response = _GUACAMOLE_RUNTIME.safe_connection_response
provision_guacamole_temporary_user = _GUACAMOLE_RUNTIME.provision_guacamole_temporary_user
delete_guacamole_temporary_user = _GUACAMOLE_RUNTIME.delete_guacamole_temporary_user
cleanup_expired_guacamole_temp_users = _GUACAMOLE_RUNTIME.cleanup_expired_guacamole_temp_users


_LAB_RESOLUTION_RUNTIME = create_lab_resolution_composition(
    _RUNTIME_POLICY,
    get_host_registry=lambda: HOSTS,
    get_guacamole_connections=lambda: load_guacamole_connections(),
    get_parse_selector=lambda: parse_guacamole_selector,
    get_normalize_key=lambda: normalize_match_key,
    get_http_get=lambda: requests.get,
    get_logger=lambda: logging,
    get_monotonic=lambda: time.monotonic,
)
resolve_lab_access_key = _LAB_RESOLUTION_RUNTIME.resolve_lab_access_key
resolve_host_by_lab = _LAB_RESOLUTION_RUNTIME.resolve_host_by_lab
resolve_lab_ids_for_host = _LAB_RESOLUTION_RUNTIME.resolve_lab_ids_for_host
resolve_lab_associations = _LAB_RESOLUTION_RUNTIME.resolve_lab_associations
refresh_lab_catalog = _LAB_RESOLUTION_RUNTIME.refresh_catalog

def build_host_inventory() -> Dict[str, Any]:
    """Build inventory while preserving the live worker patch point."""
    return _HOST_INVENTORY_RUNTIME.build_host_inventory(
        safe_entry=safe_host_inventory_entry,
    )


poll_all_hosts = _HEARTBEAT_RUNTIME.poll_all_hosts
_load_aas_persisted_heartbeat = _HEARTBEAT_RUNTIME.load_persisted_heartbeat


_RESERVATION_RUNTIME_CONTEXT = ReservationRuntimeContext(
    get_parse_bool=lambda: parse_bool,
    get_env=lambda: os.getenv,
    get_env_or_secret_file=lambda: _env_or_secret_file,
    get_parse_reservation_datetime=lambda: _parse_reservation_datetime,
    get_as_utc_datetime=lambda: _as_utc_datetime,
    get_http_get=lambda: lambda *args, **kwargs: requests.get(*args, **kwargs),
    get_sql_text=lambda: text,
    get_bindparam=lambda: bindparam,
    get_dispatch_start=lambda: lambda payload: handle_reservation_start(payload),
    get_dispatch_end=lambda: lambda payload: handle_reservation_end(payload),
    get_resolve_host_by_lab=lambda: resolve_host_by_lab,
    get_record_operation=lambda: lambda *args, **kwargs: record_reservation_operation(
        *args,
        **kwargs,
    ),
    get_logger=lambda: logging,
    get_now=lambda: lambda: datetime.now(timezone.utc),
)
ReservationOrchestrator = create_reservation_orchestrator_class(
    _RESERVATION_RUNTIME_CONTEXT
)
_ReservationOrchestratorFactory = cast(Any, ReservationOrchestrator)

_RUNTIME_SERVICES = create_runtime_services(
    power_factory=create_power_runtime,
    power_arguments={
        "extensions": APP.extensions,
        "db_engine": DB_ENGINE,
        "config_path": _RUNTIME_PATHS.power_config_path,
        "status_cache_ttl_seconds": _RUNTIME_PATHS.power_status_cache_seconds,
        "operation_store_factory": PowerOperationStore,
        "credential_store_factory": PowerCredentialStore.from_environment,
        "runtime_from_path": PowerRuntime.from_path,
        "runtime_from_config": PowerRuntime.from_config,
        "record_operation": _record_power_operation,
        "logger": logging,
    },
    reservation_factory=lambda engine, registry: _ReservationOrchestratorFactory(
        engine,
        registry,
    ),
    reservation_engine=DB_ENGINE,
    reservation_registry=HOSTS,
)
_POWER_RUNTIME_STATE = _RUNTIME_SERVICES.power_state
POWER_OPERATION_STORE = _POWER_RUNTIME_STATE.operation_store
POWER_CREDENTIAL_STORE = _POWER_RUNTIME_STATE.credential_store
POWER_RUNTIME = _POWER_RUNTIME_STATE.runtime
RESERVATION_AUTOMATOR = _RUNTIME_SERVICES.reservation_automator


_SESSION_OBSERVATION_CONTEXT = SessionObservationContext(
    get_session_observations_factory=lambda: SessionObservations,
    get_db_engine=lambda: DB_ENGINE,
    get_guacamole_db_engine=lambda: GUACAMOLE_DB_ENGINE,
    get_encrypt_secret=lambda: lambda value: _encrypt_secret_impl(
        value,
        load_fernet=_load_fernet,
    ),
    get_decrypt_secret=lambda: lambda value: _decrypt_secret_impl(
        value,
        load_fernet=_load_fernet,
    ),
    get_http_get=lambda: requests.get,
    get_http_post=lambda: requests.post,
    get_http_delete=lambda: requests.delete,
    get_sql_text=lambda: text,
    get_integrity_error_type=lambda: IntegrityError,
    get_enqueue_session_observation=lambda: enqueue_session_observation,
    get_retry_delay=lambda: _default_retry_delay_seconds_impl,
    get_to_utc=lambda: to_utc,
    get_now=lambda: lambda: datetime.now(timezone.utc),
    get_current_epoch=lambda: time.time,
    get_config=lambda: {
        "access_audit_url": ACCESS_AUDIT_URL,
        "session_observer_gateway_id": SESSION_OBSERVER_GATEWAY_ID,
        "session_observer_signing_secret": SESSION_OBSERVER_SIGNING_SECRET,
        "session_observation_outbox_enabled": SESSION_OBSERVATION_OUTBOX_ENABLED,
        "session_observation_outbox_batch_size": SESSION_OBSERVATION_OUTBOX_BATCH_SIZE,
        "session_observation_outbox_max_attempts": SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS,
        "session_observation_outbox_request_timeout_seconds": (
            SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS
        ),
        "guac_admin_user": GUAC_ADMIN_USER,
        "guac_admin_pass": GUAC_ADMIN_PASS,
        "guac_api_url": GUAC_API_URL,
        "guac_token_revocation_max_attempts": GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS,
        "guacamole_history_lookback_seconds": GUACAMOLE_HISTORY_LOOKBACK_SECONDS,
        "guacamole_history_reconciliation_retention_seconds": (
            GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS
        ),
    },
    get_logger=lambda: logging,
    get_service=lambda: _session_observations_service(),
)
_SESSION_OBSERVATION_RUNTIME = create_session_observation_runtime(
    _SESSION_OBSERVATION_CONTEXT
)
session_observation_retry_delay_seconds = _SESSION_OBSERVATION_RUNTIME.retry_delay_seconds
_encrypt_runtime_secret = _SESSION_OBSERVATION_RUNTIME.encrypt_runtime_secret
_decrypt_runtime_secret = _SESSION_OBSERVATION_RUNTIME.decrypt_runtime_secret
_session_observations_service = _SESSION_OBSERVATION_RUNTIME.create_service
enqueue_guacamole_token_revocation = _SESSION_OBSERVATION_RUNTIME.enqueue_guacamole_token_revocation


_guacamole_admin_session = _SESSION_OBSERVATION_RUNTIME.guacamole_admin_session
_guacamole_connection_history_observed = (
    _SESSION_OBSERVATION_RUNTIME.guacamole_connection_history_observed
)
_reconcile_guacamole_observations = _SESSION_OBSERVATION_RUNTIME.reconcile_guacamole_observations
process_guacamole_token_revocations = (
    _SESSION_OBSERVATION_RUNTIME.process_guacamole_token_revocations
)
enqueue_session_observation = _SESSION_OBSERVATION_RUNTIME.enqueue_session_observation


_claim_session_observation_outbox_rows = (
    _SESSION_OBSERVATION_RUNTIME.claim_session_observation_outbox_rows
)
_mark_session_observation_delivered = (
    _SESSION_OBSERVATION_RUNTIME.mark_session_observation_delivered
)
_mark_session_observation_failure = _SESSION_OBSERVATION_RUNTIME.mark_session_observation_failure
_session_observed_epoch = _SESSION_OBSERVATION_RUNTIME.session_observed_epoch
_base64url_json = _SESSION_OBSERVATION_RUNTIME.base64url_json
_session_observer_authorization = _SESSION_OBSERVATION_RUNTIME.session_observer_authorization
deliver_session_observation_outbox = _SESSION_OBSERVATION_RUNTIME.deliver_session_observation_outbox


_HOST_RELOAD_CONTEXT = HostReloadContext(
    reload_hosts=lambda **kwargs: _reload_hosts_impl(**kwargs),
    load_config=lambda: load_config(),
    registry_factory=lambda config: HostRegistry(config),
    refresh_trust_store=lambda hosts: refresh_winrm_trust_store(hosts),
    replace_registry=lambda registry: _replace_host_registry(registry),
    get_logger=lambda: logging,
)
_HOST_RELOAD_RUNTIME = create_host_reload_runtime(_HOST_RELOAD_CONTEXT)
reload_hosts = _HOST_RELOAD_RUNTIME.reload_hosts


_RUNTIME_CONTEXT = compose_worker_app(
    APP,
    globals(),
    context_factory=RuntimeContext,
    register_blueprints=register_blueprints,
)

_SCHEDULER_CONTEXT = SchedulerContext(
    get_start_scheduler=lambda: _start_scheduler_impl,
    get_scheduler_factory=lambda: lambda: BackgroundScheduler(daemon=True),
    get_poll_enabled=lambda: os.getenv("OPS_POLL_ENABLED", "false").lower() == "true",
    get_poll_interval_seconds=lambda: int(os.getenv("OPS_POLL_INTERVAL", "60")),
    get_poll_all_hosts=lambda: poll_all_hosts,
    get_register_reservation_jobs=lambda: RESERVATION_AUTOMATOR.register,
    get_cleanup_enabled=lambda: GUACAMOLE_TEMP_USER_CLEANUP_ENABLED,
    get_cleanup_interval_seconds=lambda: GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS,
    get_cleanup_expired_users=lambda: cleanup_expired_guacamole_temp_users,
    get_observation_enabled=lambda: SESSION_OBSERVATION_OUTBOX_ENABLED,
    get_observation_interval_seconds=lambda: SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS,
    get_deliver_observations=lambda: deliver_session_observation_outbox,
    get_revocation_interval_seconds=lambda: GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS,
    get_process_revocations=lambda: process_guacamole_token_revocations,
    get_now=lambda: lambda: datetime.now(timezone.utc),
    get_logger=lambda: logging,
)
_SCHEDULER_RUNTIME = create_scheduler_runtime(_SCHEDULER_CONTEXT)
start_scheduler = _SCHEDULER_RUNTIME.start_scheduler

_ENTRYPOINT_CONTEXT = EntrypointContext(
    get_configure_logging_impl=lambda: _configure_logging_impl,
    get_log_level=lambda: os.getenv("OPS_LOG_LEVEL", "INFO"),
    get_basic_config=lambda: logging.basicConfig,
    get_run_impl=lambda: _run_entrypoint_impl,
    get_configure_logging=lambda: configure_logging,
    get_refresh_trust_store=lambda: refresh_winrm_trust_store,
    get_hosts=lambda: HOSTS.all_hosts(),
    get_start_scheduler=lambda: start_scheduler,
    get_bind=lambda: os.getenv("OPS_BIND", "0.0.0.0"),
    get_port=lambda: int(os.getenv("OPS_PORT", "8081")),
    get_serve=lambda: serve,
    get_app=lambda: APP,
)
_ENTRYPOINT_RUNTIME = create_entrypoint_runtime(_ENTRYPOINT_CONTEXT)
configure_logging = _ENTRYPOINT_RUNTIME.configure_logging
main = _ENTRYPOINT_RUNTIME.main


if __name__ == "__main__":
    main()
