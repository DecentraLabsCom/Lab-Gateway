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
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union, cast

from cryptography.fernet import Fernet, InvalidToken
from flask import Response, jsonify, request, stream_with_context
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from wakeonlan import send_magic_packet
import requests
import winrm
from app_factory import create_app, register_blueprints
from entrypoint import (
    configure_logging as _configure_logging_impl,
    run as _run_entrypoint_impl,
)
from entrypoint_runtime import create_entrypoint_runtime
from app_hooks import (
    check_ops_internal_auth as _check_ops_internal_auth_impl,
    handle_unexpected_exception as _handle_unexpected_exception_impl,
    internal_error_response as _internal_error_response_impl,
    request_id_from_headers as _request_id_from_headers_impl,
    requires_ops_internal_auth as _requires_ops_internal_auth_impl,
    sanitize_log_value as _sanitize_log_value_impl,
)
from app_hooks_runtime import create_app_hooks_runtime
from runtime_context import RuntimeContext
from runtime_composition import compose_worker_app
from cryptography import x509
from cryptography.hazmat.primitives import hashes
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
from heartbeat_stream import (
    format_sse_event as _format_sse_event_impl,
    generate_heartbeat_stream as _generate_heartbeat_stream_impl,
)
from heartbeat_runtime import create_heartbeat_runtime
from heartbeat_poller import poll_all_hosts as _poll_all_hosts_impl
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
from host_reload_service import reload_hosts as _reload_hosts_impl
from host_reload_runtime import create_host_reload_runtime
from host_inventory_values import (
    safe_host_inventory_entry as _safe_host_inventory_entry_impl,
)
from host_inventory_service import (
    build_host_inventory as _build_host_inventory_impl,
    build_host_inventory_from_sources as _build_host_inventory_from_sources_impl,
)
from host_inventory_runtime import create_host_inventory_runtime
from host_discovery_values import (
    probe_labstation_http as _probe_labstation_http_impl,
    response_looks_like_labstation as _response_looks_like_labstation_impl,
)
from host_discovery_service import (
    discover_labstation_candidate as _discover_labstation_candidate_impl,
)
from host_discovery_runtime import create_host_discovery_runtime
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
from guacamole_runtime import create_guacamole_runtime
from guacamole_dsn import build_guacamole_dsn as _build_guacamole_dsn_impl
from ops_dsn import build_ops_dsn as _build_ops_dsn_impl
from datetime_values import (
    as_utc_datetime as _as_utc_datetime_impl,
    to_iso as _to_iso_impl,
    to_utc as _to_utc_impl,
)
from input_values import (
    coerce_bool as _coerce_bool_impl,
    normalize_args as _normalize_args_impl,
    parse_bool as _parse_bool_impl,
    parse_recipients as _parse_recipients_impl,
)
from input_runtime import create_input_runtime
from database_health import database_is_usable as _database_is_usable_impl
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
from host_catalog_io import (
    merge_host_configs as _merge_host_configs_impl,
    read_hosts_config as _read_hosts_config_impl,
)
from wol_service import wol_and_wait as _wol_and_wait_impl
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
from heartbeat_persistence import (
    load_persisted_heartbeat as _load_persisted_heartbeat_impl,
    persist_heartbeat as _persist_heartbeat_impl,
)
from timeline_service import (
    build_reservation_timeline as _build_reservation_timeline_impl,
    fetch_latest_heartbeat as _fetch_latest_heartbeat_impl,
    sanitize_limit as _sanitize_limit_impl,
    sanitize_offset as _sanitize_offset_impl,
    summarize_phases as _summarize_phases_impl,
)
from timeline_runtime import create_timeline_runtime
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
from winrm_runtime import create_winrm_runtime
from reservation_operations import (
    handle_reservation_end as _handle_reservation_end_impl,
    handle_reservation_start as _handle_reservation_start_impl,
)
from reservation_lifecycle_runtime import create_reservation_lifecycle_runtime
from reservation_execution_runtime import create_reservation_execution_runtime
from reservation_steps import (
    perform_command_step as _perform_command_step_impl,
    perform_wake_step as _perform_wake_step_impl,
)
from session_observations import (
    SessionObservations,
    default_retry_delay_seconds as _default_retry_delay_seconds_impl,
)
from session_observation_runtime import create_session_observation_runtime
from health_values import build_health_response as _build_health_response_impl
from operation_values import rows_to_operations as _rows_to_operations_impl
from internal_ingest_routes import handle_internal_ingest as _handle_internal_ingest_impl
from internal_ingest_runtime import create_internal_ingest_runtime
from host_provisioning_values import (
    build_provisioned_host as _build_provisioned_host_impl,
    normalize_labs as _normalize_labs_impl,
    sanitize_host_name as _sanitize_host_name_impl,
    validate_labs_against_candidates as _validate_labs_against_candidates_impl,
)
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
from scheduler_service import start_scheduler as _start_scheduler_impl
from scheduler_runtime import create_scheduler_runtime
from power.api import power_bp
from power.models import ValidationError as PowerValidationError
from power.credentials import PowerCredentialStore
from power.persistence import PowerOperationStore
from power.service import PowerRuntime

_WORKER_COMPATIBILITY_RUNTIME = create_worker_compatibility_runtime(globals())
_is_lite_gateway = _WORKER_COMPATIBILITY_RUNTIME.is_lite_gateway
_now_utc = _WORKER_COMPATIBILITY_RUNTIME.now_utc
_winrm_trust_host_or_404 = _WORKER_COMPATIBILITY_RUNTIME.winrm_trust_host_or_404
_replace_host_registry = _WORKER_COMPATIBILITY_RUNTIME.replace_host_registry
_set_host_registry = _WORKER_COMPATIBILITY_RUNTIME.set_host_registry

_APP_HOOKS_RUNTIME = create_app_hooks_runtime(globals())
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
publish_runtime_paths(_RUNTIME_PATHS, globals())


_INPUT_RUNTIME = create_input_runtime(globals())
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


APP = create_app(
    __name__,
    internal_error_response=lambda context, exc: internal_error_response(context, exc),
    internal_auth_token=lambda: OPS_INTERNAL_AUTH_TOKEN,
    internal_auth_header=lambda: OPS_INTERNAL_AUTH_HEADER,
    requires_internal_auth=_requires_ops_internal_auth,
)


_CREDENTIAL_RUNTIME = create_credential_runtime(globals())
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


_WINRM_TRUST_RUNTIME = create_winrm_trust_runtime(globals())
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


_HOST_CONFIG_RUNTIME = create_host_config_runtime(globals())
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


_HEARTBEAT_RUNTIME = create_heartbeat_runtime(globals())
to_utc = _HEARTBEAT_RUNTIME.to_utc


_WINRM_RUNTIME = create_winrm_runtime(globals())
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


_DATABASE_RUNTIME = create_database_runtime(globals())
database_is_usable = _DATABASE_RUNTIME.database_is_usable

_RESERVATION_EXECUTION_RUNTIME = create_reservation_execution_runtime(globals())
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






_DEMO_RUNTIME = create_demo_runtime(globals())
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


_RESERVATION_LIFECYCLE_RUNTIME = create_reservation_lifecycle_runtime(globals())
handle_reservation_start = _RESERVATION_LIFECYCLE_RUNTIME.handle_reservation_start
handle_reservation_end = _RESERVATION_LIFECYCLE_RUNTIME.handle_reservation_end


_TIMELINE_RUNTIME = create_timeline_runtime(globals())
_to_iso = _TIMELINE_RUNTIME.to_iso
_sanitize_limit = _TIMELINE_RUNTIME.sanitize_limit
_sanitize_offset = _TIMELINE_RUNTIME.sanitize_offset
_rows_to_operations = _TIMELINE_RUNTIME.rows_to_operations
build_reservation_timeline = _TIMELINE_RUNTIME.build_reservation_timeline
_fetch_latest_heartbeat = _TIMELINE_RUNTIME.fetch_latest_heartbeat
_summarize_phases = _TIMELINE_RUNTIME.summarize_phases

_HOST_DISCOVERY_RUNTIME = create_host_discovery_runtime(globals())
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

_WOL_RUNTIME = create_wol_runtime(globals())
wol_and_wait = _WOL_RUNTIME.wol_and_wait


_HOST_PROVISIONING_RUNTIME = create_host_provisioning_runtime(globals())
sanitize_host_name = _HOST_PROVISIONING_RUNTIME.sanitize_host_name
normalize_labs = _HOST_PROVISIONING_RUNTIME.normalize_labs
validate_labs_against_candidates = _HOST_PROVISIONING_RUNTIME.validate_labs_against_candidates
build_provisioned_host = _HOST_PROVISIONING_RUNTIME.build_provisioned_host

_HOST_INVENTORY_RUNTIME = create_host_inventory_runtime(globals())
safe_host_inventory_entry = _HOST_INVENTORY_RUNTIME.safe_host_inventory_entry

_GUACAMOLE_RUNTIME = create_guacamole_runtime(globals())
load_guacamole_connections = _GUACAMOLE_RUNTIME.load_guacamole_connections
require_guacamole_provisioner_auth = _GUACAMOLE_RUNTIME.require_guacamole_provisioner_auth
parse_guacamole_selector = _GUACAMOLE_RUNTIME.parse_guacamole_selector
safe_connection_response = _GUACAMOLE_RUNTIME.safe_connection_response
provision_guacamole_temporary_user = _GUACAMOLE_RUNTIME.provision_guacamole_temporary_user
delete_guacamole_temporary_user = _GUACAMOLE_RUNTIME.delete_guacamole_temporary_user
cleanup_expired_guacamole_temp_users = _GUACAMOLE_RUNTIME.cleanup_expired_guacamole_temp_users

build_host_inventory = _HOST_INVENTORY_RUNTIME.build_host_inventory



poll_all_hosts = _HEARTBEAT_RUNTIME.poll_all_hosts
_load_aas_persisted_heartbeat = _HEARTBEAT_RUNTIME.load_persisted_heartbeat


ReservationOrchestrator = create_reservation_orchestrator_class(globals())
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
    reservation_factory=lambda engine, registry, **_kwargs: _ReservationOrchestratorFactory(
        engine,
        registry,
    ),
    reservation_engine=DB_ENGINE,
    reservation_registry=HOSTS,
    reservation_arguments={
        "parse_bool": parse_bool,
        "get_env": os.getenv,
        "env_or_secret_file": lambda name: _env_or_secret_file(name),
        "parse_reservation_datetime": _parse_reservation_datetime,
        "as_utc_datetime": _as_utc_datetime,
        "http_get": lambda *args, **kwargs: requests.get(*args, **kwargs),
        "sql_text": text,
        "bindparam": bindparam,
        "dispatch_start": lambda payload: handle_reservation_start(payload),
        "dispatch_end": lambda payload: handle_reservation_end(payload),
        "record_operation": lambda *args, **kwargs: record_reservation_operation(*args, **kwargs),
        "logger": logging,
        "now": lambda: datetime.now(timezone.utc),
    },
)
_POWER_RUNTIME_STATE = _RUNTIME_SERVICES.power_state
POWER_OPERATION_STORE = _POWER_RUNTIME_STATE.operation_store
POWER_CREDENTIAL_STORE = _POWER_RUNTIME_STATE.credential_store
POWER_RUNTIME = _POWER_RUNTIME_STATE.runtime
RESERVATION_AUTOMATOR = _RUNTIME_SERVICES.reservation_automator


_SESSION_OBSERVATION_RUNTIME = create_session_observation_runtime(globals())
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


_INTERNAL_INGEST_RUNTIME = create_internal_ingest_runtime(globals())
ingest_guacamole_token_revocation = (
    _INTERNAL_INGEST_RUNTIME.ingest_guacamole_token_revocation
)
ingest_session_observation = _INTERNAL_INGEST_RUNTIME.ingest_session_observation


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


_HOST_RELOAD_RUNTIME = create_host_reload_runtime(globals())
reload_hosts = _HOST_RELOAD_RUNTIME.reload_hosts


_RUNTIME_CONTEXT = compose_worker_app(
    APP,
    globals(),
    context_factory=RuntimeContext,
    register_blueprints=register_blueprints,
)

_SCHEDULER_RUNTIME = create_scheduler_runtime(globals())
start_scheduler = _SCHEDULER_RUNTIME.start_scheduler

_ENTRYPOINT_RUNTIME = create_entrypoint_runtime(globals())
configure_logging = _ENTRYPOINT_RUNTIME.configure_logging
main = _ENTRYPOINT_RUNTIME.main


if __name__ == "__main__":
    main()
