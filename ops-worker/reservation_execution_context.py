"""Explicit dependencies for reservation execution and operational alerts."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ReservationExecutionContext:
    """Persistence, power, notification and command ports for reservations."""

    record_reservation_operation_impl: Callable[..., Any]
    get_db_engine: Callable[[], Any]
    get_now_utc: Callable[[], Callable[[], Any]]
    get_sql_text: Callable[[], Any]
    get_json_dumps: Callable[[], Any]
    get_check_failure_alert: Callable[[], Callable[..., Any]]
    check_failure_alert_impl: Callable[..., Any]
    get_logger: Callable[[], Any]
    get_sanitize_log_value: Callable[[], Callable[..., Any]]
    project_power_operation_impl: Callable[..., Any]
    get_record_reservation_operation: Callable[[], Callable[..., Any]]
    host_local_mode_enabled_impl: Callable[..., bool]
    get_fetch_latest_heartbeat: Callable[[], Callable[..., Any]]
    get_parse_bool: Callable[[], Callable[..., bool]]
    execute_reservation_power_phase_impl: Callable[..., Dict[str, Any]]
    get_power_runtime: Callable[[], Any]
    get_power_validation_error_type: Callable[[], Any]
    get_host_local_mode_enabled: Callable[[], Callable[..., bool]]
    should_send_failure_alert_impl: Callable[..., bool]
    get_notification_enabled: Callable[[], bool]
    get_notification_url: Callable[[], str]
    get_failure_threshold: Callable[[], int]
    get_window_seconds: Callable[[], int]
    get_cooldown_seconds: Callable[[], int]
    get_should_send_failure_alert: Callable[[], Callable[..., bool]]
    send_failure_alert_impl: Callable[..., Any]
    get_send_failure_alert: Callable[[], Callable[..., Any]]
    get_recipients: Callable[[], list[str]]
    get_token_header: Callable[[], str]
    get_token: Callable[[], str]
    get_retry_attempts: Callable[[], int]
    get_retry_backoff_seconds: Callable[[], float]
    get_http_post: Callable[[], Callable[..., Any]]
    get_sleep: Callable[[], Callable[[float], Any]]
    get_current_epoch: Callable[[], Callable[[], float]]
    notify_critical_failure_impl: Callable[..., Any]
    get_notify_critical_failure: Callable[[], Callable[..., Any]]
    perform_wake_step_impl: Callable[..., Any]
    get_wol_and_wait: Callable[[], Callable[..., Any]]
    get_run_labstation_command: Callable[[], Callable[..., Any]]
    perform_command_step_impl: Callable[..., Any]


__all__ = ["ReservationExecutionContext"]
