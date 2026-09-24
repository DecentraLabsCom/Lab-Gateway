"""Explicit runtime configuration snapshots for the Ops Worker."""

from dataclasses import dataclass
from collections.abc import Callable, Mapping, MutableMapping
import re
from typing import Any, Dict, List, Optional, Pattern, Set

from runtime_values import DEFAULT_HEARTBEAT_PATH


@dataclass(frozen=True)
class RuntimePaths:
    """Environment-derived paths and database inputs used during composition."""

    config_path: str
    dynamic_config_path: str
    credentials_path: str
    trust_path: str
    power_config_path: str
    power_status_cache_seconds: float
    mysql_dsn: Optional[str]
    guacamole_mysql_dsn: Optional[str]
    ops_mysql_database: Optional[str]
    guacamole_mysql_database: Optional[str]
    mysql_hostname: str
    mysql_port: int
    ops_mysql_user: str
    ops_mysql_password: str
    guacamole_mysql_user: str
    guacamole_mysql_password: str


@dataclass(frozen=True)
class RuntimePolicy:
    """Environment-derived operational policies used by route and scheduler wiring."""

    demo_user: str
    demo_lab_id: str
    demo_connection_id: str
    demo_heartbeat_max_age_seconds: int
    lab_status_heartbeat_max_age_seconds: int
    lab_status_target_probe_timeout_seconds: float
    lab_status_target_probe_cache_seconds: float
    demo_operation_id_re: Pattern[str]
    demo_event_actions: Dict[str, str]
    guacamole_temp_user_cleanup_enabled: bool
    guacamole_temp_user_cleanup_interval_seconds: int
    guacamole_provisioner_token: str
    guacamole_provisioner_token_header: str
    winrm_read_timeout: int
    winrm_operation_timeout: int
    winrm_allowed_transports: Set[str]
    winrm_management_cidrs: List[str]
    allowed_winrm_commands: Set[str]
    timeline_max_limit: int
    timeline_default_limit: int
    timeline_phase_lookback: int
    notification_service_url: str
    notification_service_access_token_header: str
    notification_service_access_token: str
    notification_service_enabled: bool
    notification_service_retry_attempts: int
    notification_service_retry_backoff_seconds: int
    notification_service_recipients: List[str]
    ops_alert_failure_threshold: int
    ops_alert_window_seconds: int
    ops_alert_cooldown_seconds: int
    access_audit_url: str
    session_observer_gateway_id: str
    session_observer_signing_secret: str
    session_observation_outbox_enabled: bool
    session_observation_outbox_interval_seconds: int
    session_observation_outbox_batch_size: int
    session_observation_outbox_max_attempts: int
    session_observation_outbox_request_timeout_seconds: int
    session_observation_ingest_token: str
    ops_internal_auth_token: str
    ops_internal_auth_header: str
    guac_admin_user: str
    guac_admin_pass: str
    guac_api_url: str
    guac_token_revocation_interval_seconds: int
    guac_token_revocation_max_attempts: int
    guacamole_history_lookback_seconds: int
    guacamole_history_reconciliation_retention_seconds: int
    heartbeat_sse_interval_seconds: int
    discovery_timeout_seconds: float
    discovery_labstation_ports: List[int]
    discovery_labstation_paths: List[str]
    discovery_heartbeat_paths: List[str]
    lab_catalog_url: str
    lab_catalog_token: str
    lab_catalog_token_header: str
    lab_catalog_allow_insecure: bool
    lab_catalog_timeout_seconds: float
    lab_catalog_cache_seconds: float


def load_runtime_paths(
    *,
    environ: Mapping[str, str],
    secret_loader: Callable[[str], str],
    default_config_path: str,
) -> RuntimePaths:
    """Read path, DSN and database credentials without touching application state."""
    get = environ.get
    return RuntimePaths(
        config_path=get("OPS_CONFIG", default_config_path),
        dynamic_config_path=get("OPS_DYNAMIC_CONFIG", "/app/data/hosts.json"),
        credentials_path=get("OPS_CREDENTIALS_PATH", "/app/data/winrm-credentials.json"),
        trust_path=get("OPS_WINRM_TRUST_PATH", "/app/data/winrm-certificates"),
        power_config_path=get("OPS_POWER_CONFIG", "/app/data/power-controllers.json"),
        power_status_cache_seconds=max(
            0.0,
            float(get("OPS_POWER_STATUS_CACHE_SECONDS", "5")),
        ),
        mysql_dsn=get("MYSQL_DSN"),
        guacamole_mysql_dsn=get("GUACAMOLE_MYSQL_DSN"),
        ops_mysql_database=get("OPS_MYSQL_DATABASE") or get("BLOCKCHAIN_MYSQL_DATABASE"),
        guacamole_mysql_database=get("GUACAMOLE_MYSQL_DATABASE") or get("MYSQL_DATABASE"),
        mysql_hostname=get("MYSQL_HOSTNAME") or get("MYSQL_HOST") or "mysql",
        mysql_port=int(get("MYSQL_PORT", "3306")),
        ops_mysql_user=get("OPS_BACKEND_MYSQL_USER") or "",
        ops_mysql_password=secret_loader("OPS_BACKEND_MYSQL_PASSWORD"),
        guacamole_mysql_user=get("OPS_GUACAMOLE_MYSQL_USER") or "",
        guacamole_mysql_password=secret_loader("OPS_GUACAMOLE_MYSQL_PASSWORD"),
    )


def _enabled(environ: Mapping[str, str], name: str, default: str = "true") -> bool:
    return (environ.get(name) or default).strip().lower() not in ("false", "0", "no", "off")


def is_lite_gateway(environ: Mapping[str, str]) -> bool:
    """Determine Lite mode using the same issuer/server comparison as the worker."""
    issuer = (environ.get("ISSUER") or "").strip().rstrip("/")
    if not issuer:
        return False
    server_name = (environ.get("SERVER_NAME") or "localhost").strip()
    https_port = (environ.get("HTTPS_PORT") or "443").strip()
    local_issuer = f"https://{server_name}{'' if https_port == '443' else ':' + https_port}/auth"
    return issuer != local_issuer.rstrip("/")


def load_runtime_policy(
    *,
    environ: Mapping[str, str],
    secret_loader: Callable[[str], str],
    parse_recipients: Callable[[Any, Optional[List[str]]], List[str]],
    http_header_pattern: Pattern[str],
    is_lite: Callable[[], bool],
    log_error: Callable[..., Any],
) -> RuntimePolicy:
    """Read static operational policies without constructing application state."""
    get = environ.get
    timeline_max_limit = max(1, int(get("OPS_TIMELINE_MAX_OPS", "500")))
    timeline_default_limit = max(
        1,
        min(int(get("OPS_TIMELINE_DEFAULT_LIMIT", "100")), timeline_max_limit),
    )
    access_audit_url = (get("ACCESS_AUDIT_URL") or "").strip()
    if not access_audit_url and not is_lite():
        access_audit_url = "http://blockchain-services:8080/access-audit/internal/session-observed"

    internal_auth_header = get("OPS_INTERNAL_AUTH_HEADER", "X-Ops-Internal-Token").strip()
    if not http_header_pattern.fullmatch(internal_auth_header):
        log_error("Invalid OPS_INTERNAL_AUTH_HEADER; using X-Ops-Internal-Token")
        internal_auth_header = "X-Ops-Internal-Token"

    discovery_labstation_paths = [
        path.strip() if path.strip().startswith("/") else f"/{path.strip()}"
        for path in get(
            "OPS_DISCOVERY_LABSTATION_PATHS",
            "/labstation/health,/health",
        ).split(",")
        if path.strip()
    ]
    explicit_catalog_url = (get("LAB_ADMIN_BACKEND_URL") or "").strip().rstrip("/")
    catalog_base_url = explicit_catalog_url
    catalog_token = ""
    catalog_allow_insecure = _enabled(environ, "LAB_ADMIN_BACKEND_ALLOW_INSECURE", "false")
    if catalog_base_url:
        catalog_token = secret_loader("LAB_ADMIN_BACKEND_TOKEN")
    elif not is_lite():
        # Full mode has the backend on the private Docker network.  This is
        # the default route for providers that do not configure a remote
        # backend explicitly.
        catalog_base_url = "http://blockchain-services:8080"
        catalog_token = secret_loader("LAB_MANAGER_TOKEN")
        catalog_allow_insecure = True
    catalog_url = (
        f"{catalog_base_url}/lab-admin/labs"
        if catalog_base_url and not catalog_base_url.endswith("/lab-admin/labs")
        else catalog_base_url
    )
    catalog_token_header = get(
        "LAB_ADMIN_BACKEND_TOKEN_HEADER"
        if explicit_catalog_url
        else "LAB_MANAGER_TOKEN_HEADER",
        "X-Lab-Manager-Token",
    ).strip()
    if not http_header_pattern.fullmatch(catalog_token_header):
        log_error("Invalid lab catalog token header; using X-Lab-Manager-Token")
        catalog_token_header = "X-Lab-Manager-Token"
    return RuntimePolicy(
        demo_user=(get("DEMO_USER") or "demo-lab-disabled").strip(),
        demo_lab_id=(get("DEMO_LAB_ID") or "").strip(),
        demo_connection_id=(get("DEMO_CONNECTION_ID") or "").strip(),
        demo_heartbeat_max_age_seconds=max(
            30,
            int(get("DEMO_HEARTBEAT_MAX_AGE_SECONDS", "180")),
        ),
        lab_status_heartbeat_max_age_seconds=max(
            30,
            int(get("LAB_STATUS_HEARTBEAT_MAX_AGE_SECONDS", "180")),
        ),
        lab_status_target_probe_timeout_seconds=max(
            0.2,
            float(get("LAB_STATUS_TARGET_PROBE_TIMEOUT_SECONDS", "1.5")),
        ),
        lab_status_target_probe_cache_seconds=max(
            0.0,
            float(get("LAB_STATUS_TARGET_PROBE_CACHE_SECONDS", "30")),
        ),
        demo_operation_id_re=re.compile(r"^demo:[A-Za-z0-9_.-]{1,128}$"),
        demo_event_actions={
            "start": "demo_start",
            "connected": "demo_connection",
            "expired": "demo_expiry",
            "failed": "demo_failure",
            "disconnected": "demo_disconnect",
        },
        guacamole_temp_user_cleanup_enabled=_enabled(
            environ,
            "GUACAMOLE_TEMP_USER_CLEANUP_ENABLED",
        ),
        guacamole_temp_user_cleanup_interval_seconds=max(
            60,
            int(get("GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS", "900")),
        ),
        guacamole_provisioner_token=(
            secret_loader("GUACAMOLE_PROVISIONER_TOKEN")
            or secret_loader("LAB_MANAGER_TOKEN")
            or ""
        ),
        guacamole_provisioner_token_header=get(
            "GUACAMOLE_PROVISIONER_TOKEN_HEADER", "X-Guacamole-Provisioner-Token"
        ),
        winrm_read_timeout=int(get("OPS_WINRM_READ_TIMEOUT", "30")),
        winrm_operation_timeout=int(get("OPS_WINRM_OPERATION_TIMEOUT", "20")),
        winrm_allowed_transports={
            value.strip().lower()
            for value in get("WINRM_ALLOWED_TRANSPORTS", "ntlm,kerberos,credssp").split(",")
            if value.strip()
        },
        winrm_management_cidrs=[
            value.strip()
            for value in (get("WINRM_MANAGEMENT_CIDRS") or "").split(",")
            if value.strip()
        ],
        allowed_winrm_commands={
            command.strip()
            for command in get(
                "OPS_ALLOWED_COMMANDS",
                "prepare-session,release-session,power,session,energy,status-json,recovery,account,service,wol,status",
            ).split(",")
            if command.strip()
        },
        timeline_max_limit=timeline_max_limit,
        timeline_default_limit=timeline_default_limit,
        timeline_phase_lookback=max(
            timeline_max_limit,
            int(get("OPS_TIMELINE_PHASE_LOOKBACK", "500")),
        ),
        notification_service_url=get(
            "NOTIFICATION_SERVICE_URL",
            get(
                "BLOCKCHAIN_SERVICES_NOTIFICATION_URL",
                "http://blockchain-services:8080/billing/admin/notifications/send",
            ),
        ),
        notification_service_access_token_header=get(
            "NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER", "X-Access-Token"
        ),
        notification_service_access_token=(
            secret_loader("NOTIFICATION_SERVICE_ACCESS_TOKEN")
            or secret_loader("ADMIN_ACCESS_TOKEN")
        ),
        notification_service_enabled=_enabled(environ, "NOTIFICATION_SERVICE_ENABLED"),
        notification_service_retry_attempts=max(
            0,
            int(get("NOTIFICATION_SERVICE_RETRY_ATTEMPTS", "3")),
        ),
        notification_service_retry_backoff_seconds=max(
            1,
            int(get("NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS", "5")),
        ),
        notification_service_recipients=parse_recipients(
            get("NOTIFICATION_SERVICE_RECIPIENTS"),
            None,
        ),
        ops_alert_failure_threshold=max(
            1,
            int(get("OPS_ALERT_FAILURE_THRESHOLD", "3")),
        ),
        ops_alert_window_seconds=max(
            60,
            int(get("OPS_ALERT_WINDOW_SECONDS", "300")),
        ),
        ops_alert_cooldown_seconds=max(
            60,
            int(get("OPS_ALERT_COOLDOWN_SECONDS", "900")),
        ),
        access_audit_url=access_audit_url,
        session_observer_gateway_id=(get("SESSION_OBSERVER_GATEWAY_ID") or "").strip(),
        session_observer_signing_secret=secret_loader("SESSION_OBSERVER_SIGNING_SECRET").strip(),
        session_observation_outbox_enabled=_enabled(
            environ,
            "SESSION_OBSERVATION_OUTBOX_ENABLED",
        ),
        session_observation_outbox_interval_seconds=max(
            1,
            int(get("SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS", "5")),
        ),
        session_observation_outbox_batch_size=max(
            1,
            int(get("SESSION_OBSERVATION_OUTBOX_BATCH_SIZE", "20")),
        ),
        session_observation_outbox_max_attempts=max(
            1,
            int(get("SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS", "20")),
        ),
        session_observation_outbox_request_timeout_seconds=max(
            1,
            int(get("SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS", "5")),
        ),
        session_observation_ingest_token=secret_loader("SESSION_OBSERVATION_INGEST_TOKEN"),
        ops_internal_auth_token=secret_loader("OPS_INTERNAL_AUTH_TOKEN").strip(),
        ops_internal_auth_header=internal_auth_header,
        guac_admin_user=get("GUAC_ADMIN_USER") or "",
        guac_admin_pass=secret_loader("GUAC_ADMIN_PASS"),
        guac_api_url=get("GUAC_API_URL", "http://guacamole:8080/guacamole/api").rstrip("/"),
        guac_token_revocation_interval_seconds=max(
            1,
            int(get("GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS", "10")),
        ),
        guac_token_revocation_max_attempts=max(
            1,
            int(get("GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS", "20")),
        ),
        guacamole_history_lookback_seconds=max(
            0,
            int(get("GUACAMOLE_HISTORY_LOOKBACK_SECONDS", "30")),
        ),
        guacamole_history_reconciliation_retention_seconds=max(
            0,
            int(get("GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS", "300")),
        ),
        heartbeat_sse_interval_seconds=max(
            1,
            int(get("OPS_HEARTBEAT_SSE_INTERVAL_SECONDS", "10")),
        ),
        discovery_timeout_seconds=max(
            0.2,
            float(get("OPS_DISCOVERY_TIMEOUT_SECONDS", "1.5")),
        ),
        discovery_labstation_ports=[
            int(port.strip())
            for port in get("OPS_DISCOVERY_LABSTATION_PORTS", "8765,8088").split(",")
            if port.strip().isdigit()
        ],
        discovery_labstation_paths=discovery_labstation_paths,
        discovery_heartbeat_paths=[
            path.strip()
            for path in (
                get(
                    "OPS_DISCOVERY_HEARTBEAT_PATHS",
                    DEFAULT_HEARTBEAT_PATH,
                )
            ).split(",")
            if path.strip()
        ],
        lab_catalog_url=catalog_url,
        lab_catalog_token=catalog_token,
        lab_catalog_token_header=catalog_token_header,
        lab_catalog_allow_insecure=catalog_allow_insecure,
        lab_catalog_timeout_seconds=max(
            0.2,
            float(get("LAB_ADMIN_BACKEND_TIMEOUT_SECONDS", "30")),
        ),
        lab_catalog_cache_seconds=max(
            0.0,
            float(get("LAB_CATALOG_CACHE_SECONDS", "15")),
        ),
    )


def _publish_dataclass_attributes(
    value: Any,
    namespace: MutableMapping[str, Any],
    exports: tuple[tuple[str, str], ...],
) -> None:
    for public_name, attribute_name in exports:
        namespace[public_name] = getattr(value, attribute_name)


def publish_runtime_paths(
    paths: RuntimePaths,
    namespace: MutableMapping[str, Any],
) -> None:
    """Publish path and database values under the worker's historical names."""
    _publish_dataclass_attributes(
        paths,
        namespace,
        (
            ("CONFIG_PATH", "config_path"),
            ("DYNAMIC_CONFIG_PATH", "dynamic_config_path"),
            ("OPS_CREDENTIALS_PATH", "credentials_path"),
            ("OPS_WINRM_TRUST_PATH", "trust_path"),
            ("POWER_CONFIG_PATH", "power_config_path"),
            ("POWER_STATUS_CACHE_SECONDS", "power_status_cache_seconds"),
            ("MYSQL_DSN", "mysql_dsn"),
            ("GUACAMOLE_MYSQL_DSN", "guacamole_mysql_dsn"),
            ("OPS_MYSQL_DATABASE", "ops_mysql_database"),
            ("GUACAMOLE_MYSQL_DATABASE", "guacamole_mysql_database"),
            ("MYSQL_HOSTNAME", "mysql_hostname"),
            ("MYSQL_PORT", "mysql_port"),
            ("OPS_MYSQL_USER", "ops_mysql_user"),
            ("OPS_MYSQL_PASSWORD", "ops_mysql_password"),
            ("GUACAMOLE_MYSQL_USER", "guacamole_mysql_user"),
            ("GUACAMOLE_MYSQL_PASSWORD", "guacamole_mysql_password"),
        ),
    )


def publish_runtime_policy(
    policy: RuntimePolicy,
    namespace: MutableMapping[str, Any],
) -> None:
    """Publish operational policy values under the worker's historical names."""
    _publish_dataclass_attributes(
        policy,
        namespace,
        (
            ("DEMO_USER", "demo_user"),
            ("DEMO_LAB_ID", "demo_lab_id"),
            ("DEMO_CONNECTION_ID", "demo_connection_id"),
            ("DEMO_HEARTBEAT_MAX_AGE_SECONDS", "demo_heartbeat_max_age_seconds"),
            ("LAB_STATUS_HEARTBEAT_MAX_AGE_SECONDS", "lab_status_heartbeat_max_age_seconds"),
            (
                "LAB_STATUS_TARGET_PROBE_TIMEOUT_SECONDS",
                "lab_status_target_probe_timeout_seconds",
            ),
            (
                "LAB_STATUS_TARGET_PROBE_CACHE_SECONDS",
                "lab_status_target_probe_cache_seconds",
            ),
            ("DEMO_OPERATION_ID_RE", "demo_operation_id_re"),
            ("DEMO_EVENT_ACTIONS", "demo_event_actions"),
            ("GUACAMOLE_TEMP_USER_CLEANUP_ENABLED", "guacamole_temp_user_cleanup_enabled"),
            (
                "GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS",
                "guacamole_temp_user_cleanup_interval_seconds",
            ),
            ("GUACAMOLE_PROVISIONER_TOKEN", "guacamole_provisioner_token"),
            ("GUACAMOLE_PROVISIONER_TOKEN_HEADER", "guacamole_provisioner_token_header"),
            ("WINRM_READ_TIMEOUT", "winrm_read_timeout"),
            ("WINRM_OPERATION_TIMEOUT", "winrm_operation_timeout"),
            ("WINRM_ALLOWED_TRANSPORTS", "winrm_allowed_transports"),
            ("WINRM_MANAGEMENT_CIDRS", "winrm_management_cidrs"),
            ("ALLOWED_WINRM_COMMANDS", "allowed_winrm_commands"),
            ("TIMELINE_MAX_LIMIT", "timeline_max_limit"),
            ("TIMELINE_DEFAULT_LIMIT", "timeline_default_limit"),
            ("TIMELINE_PHASE_LOOKBACK", "timeline_phase_lookback"),
            ("NOTIFICATION_SERVICE_URL", "notification_service_url"),
            (
                "NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER",
                "notification_service_access_token_header",
            ),
            ("NOTIFICATION_SERVICE_ACCESS_TOKEN", "notification_service_access_token"),
            ("NOTIFICATION_SERVICE_ENABLED", "notification_service_enabled"),
            ("NOTIFICATION_SERVICE_RETRY_ATTEMPTS", "notification_service_retry_attempts"),
            (
                "NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS",
                "notification_service_retry_backoff_seconds",
            ),
            ("NOTIFICATION_SERVICE_RECIPIENTS", "notification_service_recipients"),
            ("OPS_ALERT_FAILURE_THRESHOLD", "ops_alert_failure_threshold"),
            ("OPS_ALERT_WINDOW_SECONDS", "ops_alert_window_seconds"),
            ("OPS_ALERT_COOLDOWN_SECONDS", "ops_alert_cooldown_seconds"),
            ("ACCESS_AUDIT_URL", "access_audit_url"),
            ("SESSION_OBSERVER_GATEWAY_ID", "session_observer_gateway_id"),
            ("SESSION_OBSERVER_SIGNING_SECRET", "session_observer_signing_secret"),
            ("SESSION_OBSERVATION_OUTBOX_ENABLED", "session_observation_outbox_enabled"),
            (
                "SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS",
                "session_observation_outbox_interval_seconds",
            ),
            (
                "SESSION_OBSERVATION_OUTBOX_BATCH_SIZE",
                "session_observation_outbox_batch_size",
            ),
            (
                "SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS",
                "session_observation_outbox_max_attempts",
            ),
            (
                "SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS",
                "session_observation_outbox_request_timeout_seconds",
            ),
            ("SESSION_OBSERVATION_INGEST_TOKEN", "session_observation_ingest_token"),
            ("OPS_INTERNAL_AUTH_TOKEN", "ops_internal_auth_token"),
            ("OPS_INTERNAL_AUTH_HEADER", "ops_internal_auth_header"),
            ("GUAC_ADMIN_USER", "guac_admin_user"),
            ("GUAC_ADMIN_PASS", "guac_admin_pass"),
            ("GUAC_API_URL", "guac_api_url"),
            (
                "GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS",
                "guac_token_revocation_interval_seconds",
            ),
            (
                "GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS",
                "guac_token_revocation_max_attempts",
            ),
            (
                "GUACAMOLE_HISTORY_LOOKBACK_SECONDS",
                "guacamole_history_lookback_seconds",
            ),
            (
                "GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS",
                "guacamole_history_reconciliation_retention_seconds",
            ),
            ("HEARTBEAT_SSE_INTERVAL_SECONDS", "heartbeat_sse_interval_seconds"),
            ("DISCOVERY_TIMEOUT_SECONDS", "discovery_timeout_seconds"),
            ("DISCOVERY_LABSTATION_PORTS", "discovery_labstation_ports"),
            ("DISCOVERY_LABSTATION_PATHS", "discovery_labstation_paths"),
            ("DISCOVERY_HEARTBEAT_PATHS", "discovery_heartbeat_paths"),
        ),
    )


__all__ = [
    "RuntimePaths",
    "RuntimePolicy",
    "is_lite_gateway",
    "load_runtime_paths",
    "load_runtime_policy",
    "publish_runtime_paths",
    "publish_runtime_policy",
]
