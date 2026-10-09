"""Environment-backed configuration for the FMU Runner."""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_or_secret_file(
    name: str,
    default: str = "",
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Read an environment value, falling back to a mounted secret file."""
    values = os.environ if environ is None else environ
    value = values.get(name)
    if value:
        return value
    path = values.get(f"{name}_FILE")
    if not path:
        return default
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        logging.warning("Unable to read secret file for %s", name)
        return default


def _default_access_audit_url(redeem_url: str) -> str:
    parsed = urlparse(redeem_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunparse(parsed._replace(
        path="/access-audit/internal/session-observed",
        params="",
        query="",
        fragment="",
    ))


def _flag(values: Mapping[str, str], name: str, default: str = "false") -> bool:
    return values.get(name, default).strip().lower() in _TRUE_VALUES


@dataclass(frozen=True)
class FmuRunnerConfig:
    fmu_data_path: str
    aas_link_data_path: Path
    aas_catalog_path: Path
    max_simulation_timeout: int
    max_concurrent_per_model: int
    fmu_worker_address_space_limit: int
    max_stop_time: float
    min_step_size: float
    history_db_path: str
    ws_session_queue_size: int
    ws_heartbeat_seconds: float
    ws_expiring_notice_seconds: int
    ws_attach_grace_seconds: int
    ws_cleanup_seconds: float
    internal_ws_token: str
    auth_session_ticket_issue_url: str
    auth_session_ticket_redeem_url: str
    auth_session_ticket_internal_token: str
    session_observer_gateway_id: str
    session_observer_signing_secret: str
    access_audit_url: str
    fmu_proxy_runtime_path: str
    fmu_proxy_gateway_ws_url: str
    fmu_proxy_signing_key: str
    fmu_backend_mode: str
    fmu_local_dev_mode: bool
    fmu_local_realtime_enabled: bool
    fmu_local_executor_base_url: str
    fmu_local_executor_internal_token: str
    fmu_station_base_url: str
    fmu_station_internal_token: str
    fmu_station_request_timeout: float
    fmu_session_observation_max_attempts: int
    proxy_download_rate_limit_per_minute: int
    ws_create_rate_limit_per_minute: int


def load_config(environ: Mapping[str, str] | None = None) -> FmuRunnerConfig:
    """Parse the FMU Runner environment while preserving current defaults."""
    values = os.environ if environ is None else environ
    redeem_url = values.get(
        "AUTH_SESSION_TICKET_REDEEM_URL",
        "http://blockchain-services:8080/auth/fmu/session-ticket/redeem",
    )
    configured_audit_url = values.get("ACCESS_AUDIT_URL", "").strip()
    return FmuRunnerConfig(
        fmu_data_path=values.get("FMU_DATA_PATH", "/app/fmu-data"),
        aas_link_data_path=Path(values.get("AAS_LINK_DATA_PATH", "/app/data/aas-links")),
        aas_catalog_path=Path(values.get("AAS_CATALOG_PATH", "/app/data/aasx")),
        max_simulation_timeout=int(values.get("MAX_SIMULATION_TIMEOUT", "300")),
        max_concurrent_per_model=int(values.get("MAX_CONCURRENT_PER_MODEL", "10")),
        fmu_worker_address_space_limit=int(values.get(
            "FMU_WORKER_ADDRESS_SPACE_LIMIT",
            str(2 * 1024 ** 3),
        )),
        max_stop_time=float(values.get("MAX_STOP_TIME", "86400")),
        min_step_size=float(values.get("MIN_STEP_SIZE", "1e-6")),
        history_db_path=values.get("HISTORY_DB_PATH", "/app/data/history.db"),
        ws_session_queue_size=int(values.get("WS_SESSION_QUEUE_SIZE", "64")),
        ws_heartbeat_seconds=float(values.get("WS_HEARTBEAT_SECONDS", "15")),
        ws_expiring_notice_seconds=int(values.get("WS_EXPIRING_NOTICE_SECONDS", "60")),
        ws_attach_grace_seconds=int(values.get("WS_ATTACH_GRACE_SECONDS", "120")),
        ws_cleanup_seconds=float(values.get("WS_CLEANUP_SECONDS", "15")),
        internal_ws_token=_env_or_secret_file("FMU_INTERNAL_WS_TOKEN", environ=values),
        auth_session_ticket_issue_url=values.get(
            "AUTH_SESSION_TICKET_ISSUE_URL",
            "http://blockchain-services:8080/auth/fmu/session-ticket/issue",
        ),
        auth_session_ticket_redeem_url=redeem_url,
        auth_session_ticket_internal_token=_env_or_secret_file(
            "AUTH_SESSION_TICKET_INTERNAL_TOKEN", environ=values,
        ),
        session_observer_gateway_id=values.get("SESSION_OBSERVER_GATEWAY_ID", "").strip().lower(),
        session_observer_signing_secret=_env_or_secret_file(
            "SESSION_OBSERVER_SIGNING_SECRET", environ=values,
        ).strip(),
        access_audit_url=configured_audit_url or _default_access_audit_url(redeem_url),
        fmu_proxy_runtime_path=values.get("FMU_PROXY_RUNTIME_PATH", "/app/fmu-proxy-runtime"),
        fmu_proxy_gateway_ws_url=values.get("FMU_PROXY_GATEWAY_WS_URL", ""),
        fmu_proxy_signing_key=_env_or_secret_file("FMU_PROXY_SIGNING_KEY", environ=values),
        fmu_backend_mode=values.get("FMU_BACKEND_MODE", "station").strip().lower(),
        fmu_local_dev_mode=_flag(values, "FMU_LOCAL_DEV_MODE"),
        fmu_local_realtime_enabled=_flag(values, "FMU_LOCAL_REALTIME_ENABLED"),
        fmu_local_executor_base_url=values.get("FMU_LOCAL_EXECUTOR_BASE_URL", "").strip(),
        fmu_local_executor_internal_token=_env_or_secret_file(
            "FMU_LOCAL_EXECUTOR_INTERNAL_TOKEN", environ=values,
        ).strip(),
        fmu_station_base_url=values.get("FMU_STATION_BASE_URL", "").strip(),
        fmu_station_internal_token=_env_or_secret_file(
            "FMU_STATION_INTERNAL_TOKEN", environ=values,
        ).strip(),
        fmu_station_request_timeout=float(values.get("FMU_STATION_REQUEST_TIMEOUT", "10")),
        fmu_session_observation_max_attempts=max(
            1, int(values.get("FMU_SESSION_OBSERVATION_MAX_ATTEMPTS", "3")),
        ),
        proxy_download_rate_limit_per_minute=int(
            values.get("PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE", "20"),
        ),
        ws_create_rate_limit_per_minute=int(values.get("WS_CREATE_RATE_LIMIT_PER_MINUTE", "30")),
    )


CONFIG = load_config()


__all__ = ["FmuRunnerConfig", "CONFIG", "load_config"]
