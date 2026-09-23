import re

from runtime_config import (
    RuntimePaths,
    RuntimePolicy,
    is_lite_gateway,
    load_runtime_paths,
    load_runtime_policy,
    publish_runtime_paths,
    publish_runtime_policy,
)


def test_load_runtime_paths_contract_preserves_defaults_precedence_and_secret_loading():
    secrets = []
    config = load_runtime_paths(
        environ={
            "OPS_DYNAMIC_CONFIG": "/data/dynamic.json",
            "OPS_CREDENTIALS_PATH": "/data/credentials.json",
            "OPS_WINRM_TRUST_PATH": "/data/trust",
            "OPS_POWER_CONFIG": "/data/power.json",
            "OPS_POWER_STATUS_CACHE_SECONDS": "0",
            "MYSQL_DSN": "mysql://explicit",
            "OPS_MYSQL_DATABASE": "ops-db",
            "BLOCKCHAIN_MYSQL_DATABASE": "fallback-db",
            "MYSQL_DATABASE": "guac-db",
            "MYSQL_HOST": "db.internal",
            "MYSQL_PORT": "3307",
            "OPS_BACKEND_MYSQL_USER": "ops-user",
            "OPS_GUACAMOLE_MYSQL_USER": "guac-user",
        },
        secret_loader=lambda name: secrets.append(name) or f"secret:{name}",
        default_config_path="/app/hosts.json",
    )

    assert isinstance(config, RuntimePaths)
    assert config.config_path == "/app/hosts.json"
    assert config.dynamic_config_path == "/data/dynamic.json"
    assert config.credentials_path == "/data/credentials.json"
    assert config.trust_path == "/data/trust"
    assert config.power_config_path == "/data/power.json"
    assert config.power_status_cache_seconds == 0.0
    assert config.mysql_dsn == "mysql://explicit"
    assert config.guacamole_mysql_dsn is None
    assert config.ops_mysql_database == "ops-db"
    assert config.guacamole_mysql_database == "guac-db"
    assert config.mysql_hostname == "db.internal"
    assert config.mysql_port == 3307
    assert config.ops_mysql_user == "ops-user"
    assert config.ops_mysql_password == "secret:OPS_BACKEND_MYSQL_PASSWORD"
    assert config.guacamole_mysql_user == "guac-user"
    assert config.guacamole_mysql_password == "secret:OPS_GUACAMOLE_MYSQL_PASSWORD"
    assert secrets == [
        "OPS_BACKEND_MYSQL_PASSWORD",
        "OPS_GUACAMOLE_MYSQL_PASSWORD",
    ]


def test_load_runtime_paths_contract_uses_host_and_database_fallbacks():
    config = load_runtime_paths(
        environ={
            "OPS_CONFIG": "custom-hosts.json",
            "BLOCKCHAIN_MYSQL_DATABASE": "backend-db",
            "MYSQL_DATABASE": "guacamole-db",
        },
        secret_loader=lambda _name: "",
        default_config_path="default-hosts.json",
    )

    assert config.config_path == "custom-hosts.json"
    assert config.dynamic_config_path == "/app/data/hosts.json"
    assert config.credentials_path == "/app/data/winrm-credentials.json"
    assert config.trust_path == "/app/data/winrm-certificates"
    assert config.power_config_path == "/app/data/power-controllers.json"
    assert config.power_status_cache_seconds == 5.0
    assert config.ops_mysql_database == "backend-db"
    assert config.guacamole_mysql_database == "guacamole-db"
    assert config.mysql_hostname == "mysql"
    assert config.mysql_port == 3306


def test_load_runtime_policy_contract_preserves_operational_defaults_and_precedence():
    secrets = {
        "GUACAMOLE_PROVISIONER_TOKEN": "provisioner-secret",
        "LAB_MANAGER_TOKEN": "legacy-secret",
        "NOTIFICATION_SERVICE_ACCESS_TOKEN": "notification-secret",
        "ADMIN_ACCESS_TOKEN": "legacy-admin-secret",
        "SESSION_OBSERVER_SIGNING_SECRET": "observer-secret",
        "SESSION_OBSERVATION_INGEST_TOKEN": "ingest-secret",
        "OPS_INTERNAL_AUTH_TOKEN": "internal-secret",
        "GUAC_ADMIN_PASS": "guac-pass",
    }
    config = load_runtime_policy(
        environ={
            "DEMO_USER": " demo ",
            "DEMO_LAB_ID": "42",
            "DEMO_CONNECTION_ID": "7",
            "DEMO_HEARTBEAT_MAX_AGE_SECONDS": "20",
            "LAB_STATUS_HEARTBEAT_MAX_AGE_SECONDS": "45",
            "GUACAMOLE_TEMP_USER_CLEANUP_ENABLED": "off",
            "GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS": "30",
            "GUACAMOLE_PROVISIONER_TOKEN_HEADER": "X-Provisioner",
            "OPS_WINRM_READ_TIMEOUT": "40",
            "OPS_WINRM_OPERATION_TIMEOUT": "25",
            "WINRM_ALLOWED_TRANSPORTS": " NTLM, kerberos ",
            "WINRM_MANAGEMENT_CIDRS": "10.0.0.0/8, 192.168.0.0/16",
            "OPS_ALLOWED_COMMANDS": "status, power",
            "OPS_TIMELINE_MAX_OPS": "50",
            "OPS_TIMELINE_DEFAULT_LIMIT": "100",
            "OPS_TIMELINE_PHASE_LOOKBACK": "10",
            "BLOCKCHAIN_SERVICES_NOTIFICATION_URL": "http://notify/send",
            "NOTIFICATION_SERVICE_ENABLED": "no",
            "NOTIFICATION_SERVICE_RECIPIENTS": "ops@example.com, support@example.com",
            "NOTIFICATION_SERVICE_RETRY_ATTEMPTS": "0",
            "NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS": "1",
            "OPS_ALERT_FAILURE_THRESHOLD": "0",
            "OPS_ALERT_WINDOW_SECONDS": "30",
            "OPS_ALERT_COOLDOWN_SECONDS": "30",
            "SESSION_OBSERVER_GATEWAY_ID": "gateway-a",
            "SESSION_OBSERVATION_OUTBOX_ENABLED": "false",
            "SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS": "0",
            "SESSION_OBSERVATION_OUTBOX_BATCH_SIZE": "0",
            "SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS": "0",
            "SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS": "0",
            "GUAC_ADMIN_USER": "admin",
            "GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS": "0",
            "GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS": "0",
            "GUACAMOLE_HISTORY_LOOKBACK_SECONDS": "-1",
            "GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS": "-1",
            "OPS_HEARTBEAT_SSE_INTERVAL_SECONDS": "0",
            "OPS_DISCOVERY_TIMEOUT_SECONDS": "0.1",
            "OPS_DISCOVERY_LABSTATION_PORTS": "8765, 8088",
            "OPS_DISCOVERY_LABSTATION_PATHS": "health,/ready",
            "OPS_DISCOVERY_HEARTBEAT_PATHS": "C:\\heartbeat.json",
        },
        secret_loader=lambda name: secrets.get(name, ""),
        parse_recipients=lambda value, default: [
            part.strip() for part in str(value or "").split(",") if part.strip()
        ],
        http_header_pattern=re.compile(r"^[A-Za-z0-9-]+$"),
        is_lite=lambda: False,
        log_error=lambda *_args: None,
    )

    assert isinstance(config, RuntimePolicy)
    assert config.lab_catalog_timeout_seconds == 30.0
    assert config.demo_user == "demo"
    assert config.demo_heartbeat_max_age_seconds == 30
    assert config.lab_status_heartbeat_max_age_seconds == 45
    assert config.guacamole_temp_user_cleanup_enabled is False
    assert config.guacamole_temp_user_cleanup_interval_seconds == 60
    assert config.guacamole_provisioner_token == "provisioner-secret"
    assert config.winrm_allowed_transports == {"ntlm", "kerberos"}
    assert config.winrm_management_cidrs == ["10.0.0.0/8", "192.168.0.0/16"]
    assert config.allowed_winrm_commands == {"status", "power"}
    assert config.timeline_max_limit == 50
    assert config.timeline_default_limit == 50
    assert config.timeline_phase_lookback == 50
    assert config.notification_service_url == "http://notify/send"
    assert config.notification_service_enabled is False
    assert config.notification_service_retry_attempts == 0
    assert config.notification_service_recipients == ["ops@example.com", "support@example.com"]
    assert config.ops_alert_failure_threshold == 1
    assert config.ops_alert_window_seconds == 60
    assert config.ops_alert_cooldown_seconds == 60
    assert config.session_observation_outbox_interval_seconds == 1
    assert config.session_observation_outbox_batch_size == 1
    assert config.session_observation_outbox_max_attempts == 1
    assert config.session_observation_outbox_request_timeout_seconds == 1
    assert config.access_audit_url == "http://blockchain-services:8080/access-audit/internal/session-observed"
    assert config.guac_api_url == "http://guacamole:8080/guacamole/api"
    assert config.guacamole_history_lookback_seconds == 0
    assert config.discovery_timeout_seconds == 0.2
    assert config.discovery_labstation_ports == [8765, 8088]
    assert config.discovery_labstation_paths == ["/health", "/ready"]
    assert config.discovery_heartbeat_paths == ["C:\\heartbeat.json"]
    assert is_lite_gateway({"ISSUER": "https://other.example/auth"}) is True


def test_load_runtime_policy_contract_preserves_explicit_empty_values_and_fails_closed_header():
    errors = []
    config = load_runtime_policy(
        environ={
            "WINRM_ALLOWED_TRANSPORTS": "",
            "OPS_ALLOWED_COMMANDS": "",
            "NOTIFICATION_SERVICE_URL": "",
            "NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER": "",
            "OPS_DISCOVERY_LABSTATION_PORTS": "",
            "OPS_DISCOVERY_LABSTATION_PATHS": "",
            "OPS_DISCOVERY_HEARTBEAT_PATHS": "",
            "GUAC_API_URL": "",
            "OPS_INTERNAL_AUTH_HEADER": "",
        },
        secret_loader=lambda _name: "",
        parse_recipients=lambda value, default=None: [],
        http_header_pattern=re.compile(r"^[A-Za-z0-9-]+$"),
        is_lite=lambda: True,
        log_error=lambda *args: errors.append(args),
    )

    assert config.winrm_allowed_transports == set()
    assert config.allowed_winrm_commands == set()
    assert config.notification_service_url == ""
    assert config.notification_service_access_token_header == ""
    assert config.discovery_labstation_ports == []
    assert config.discovery_labstation_paths == []
    assert config.discovery_heartbeat_paths == []
    assert config.guac_api_url == ""
    assert config.ops_internal_auth_header == "X-Ops-Internal-Token"
    assert errors == [("Invalid OPS_INTERNAL_AUTH_HEADER; using X-Ops-Internal-Token",)]


def test_runtime_config_publication_preserves_legacy_path_and_policy_names():
    paths = RuntimePaths(
        config_path="config",
        dynamic_config_path="dynamic",
        credentials_path="credentials",
        trust_path="trust",
        power_config_path="power",
        power_status_cache_seconds=1.5,
        mysql_dsn="ops-dsn",
        guacamole_mysql_dsn="guac-dsn",
        ops_mysql_database="ops-db",
        guacamole_mysql_database="guac-db",
        mysql_hostname="mysql",
        mysql_port=3306,
        ops_mysql_user="ops-user",
        ops_mysql_password="ops-pass",
        guacamole_mysql_user="guac-user",
        guacamole_mysql_password="guac-pass",
    )
    namespace = {}

    publish_runtime_paths(paths, namespace)

    assert namespace == {
        "CONFIG_PATH": "config",
        "DYNAMIC_CONFIG_PATH": "dynamic",
        "OPS_CREDENTIALS_PATH": "credentials",
        "OPS_WINRM_TRUST_PATH": "trust",
        "POWER_CONFIG_PATH": "power",
        "POWER_STATUS_CACHE_SECONDS": 1.5,
        "MYSQL_DSN": "ops-dsn",
        "GUACAMOLE_MYSQL_DSN": "guac-dsn",
        "OPS_MYSQL_DATABASE": "ops-db",
        "GUACAMOLE_MYSQL_DATABASE": "guac-db",
        "MYSQL_HOSTNAME": "mysql",
        "MYSQL_PORT": 3306,
        "OPS_MYSQL_USER": "ops-user",
        "OPS_MYSQL_PASSWORD": "ops-pass",
        "GUACAMOLE_MYSQL_USER": "guac-user",
        "GUACAMOLE_MYSQL_PASSWORD": "guac-pass",
    }

    policy = load_runtime_policy(
        environ={},
        secret_loader=lambda _name: "",
        parse_recipients=lambda _value, _default: [],
        http_header_pattern=re.compile(r"^[A-Za-z0-9-]+$"),
        is_lite=lambda: False,
        log_error=lambda *_args: None,
    )
    publish_runtime_policy(policy, namespace)

    expected_policy_names = {
        "DEMO_USER": "demo_user",
        "DEMO_LAB_ID": "demo_lab_id",
        "DEMO_CONNECTION_ID": "demo_connection_id",
        "DEMO_HEARTBEAT_MAX_AGE_SECONDS": "demo_heartbeat_max_age_seconds",
        "LAB_STATUS_HEARTBEAT_MAX_AGE_SECONDS": "lab_status_heartbeat_max_age_seconds",
        "DEMO_OPERATION_ID_RE": "demo_operation_id_re",
        "DEMO_EVENT_ACTIONS": "demo_event_actions",
        "GUACAMOLE_TEMP_USER_CLEANUP_ENABLED": "guacamole_temp_user_cleanup_enabled",
        "GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS": "guacamole_temp_user_cleanup_interval_seconds",
        "GUACAMOLE_PROVISIONER_TOKEN": "guacamole_provisioner_token",
        "GUACAMOLE_PROVISIONER_TOKEN_HEADER": "guacamole_provisioner_token_header",
        "WINRM_READ_TIMEOUT": "winrm_read_timeout",
        "WINRM_OPERATION_TIMEOUT": "winrm_operation_timeout",
        "WINRM_ALLOWED_TRANSPORTS": "winrm_allowed_transports",
        "WINRM_MANAGEMENT_CIDRS": "winrm_management_cidrs",
        "ALLOWED_WINRM_COMMANDS": "allowed_winrm_commands",
        "TIMELINE_MAX_LIMIT": "timeline_max_limit",
        "TIMELINE_DEFAULT_LIMIT": "timeline_default_limit",
        "TIMELINE_PHASE_LOOKBACK": "timeline_phase_lookback",
        "NOTIFICATION_SERVICE_URL": "notification_service_url",
        "NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER": "notification_service_access_token_header",
        "NOTIFICATION_SERVICE_ACCESS_TOKEN": "notification_service_access_token",
        "NOTIFICATION_SERVICE_ENABLED": "notification_service_enabled",
        "NOTIFICATION_SERVICE_RETRY_ATTEMPTS": "notification_service_retry_attempts",
        "NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS": "notification_service_retry_backoff_seconds",
        "NOTIFICATION_SERVICE_RECIPIENTS": "notification_service_recipients",
        "OPS_ALERT_FAILURE_THRESHOLD": "ops_alert_failure_threshold",
        "OPS_ALERT_WINDOW_SECONDS": "ops_alert_window_seconds",
        "OPS_ALERT_COOLDOWN_SECONDS": "ops_alert_cooldown_seconds",
        "ACCESS_AUDIT_URL": "access_audit_url",
        "SESSION_OBSERVER_GATEWAY_ID": "session_observer_gateway_id",
        "SESSION_OBSERVER_SIGNING_SECRET": "session_observer_signing_secret",
        "SESSION_OBSERVATION_OUTBOX_ENABLED": "session_observation_outbox_enabled",
        "SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS": "session_observation_outbox_interval_seconds",
        "SESSION_OBSERVATION_OUTBOX_BATCH_SIZE": "session_observation_outbox_batch_size",
        "SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS": "session_observation_outbox_max_attempts",
        "SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS": "session_observation_outbox_request_timeout_seconds",
        "SESSION_OBSERVATION_INGEST_TOKEN": "session_observation_ingest_token",
        "OPS_INTERNAL_AUTH_TOKEN": "ops_internal_auth_token",
        "OPS_INTERNAL_AUTH_HEADER": "ops_internal_auth_header",
        "GUAC_ADMIN_USER": "guac_admin_user",
        "GUAC_ADMIN_PASS": "guac_admin_pass",
        "GUAC_API_URL": "guac_api_url",
        "GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS": "guac_token_revocation_interval_seconds",
        "GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS": "guac_token_revocation_max_attempts",
        "GUACAMOLE_HISTORY_LOOKBACK_SECONDS": "guacamole_history_lookback_seconds",
        "GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS": "guacamole_history_reconciliation_retention_seconds",
        "HEARTBEAT_SSE_INTERVAL_SECONDS": "heartbeat_sse_interval_seconds",
        "DISCOVERY_TIMEOUT_SECONDS": "discovery_timeout_seconds",
        "DISCOVERY_LABSTATION_PORTS": "discovery_labstation_ports",
        "DISCOVERY_LABSTATION_PATHS": "discovery_labstation_paths",
        "DISCOVERY_HEARTBEAT_PATHS": "discovery_heartbeat_paths",
    }
    assert {name: namespace[name] for name in expected_policy_names} == {
        name: getattr(policy, field) for name, field in expected_policy_names.items()
    }
