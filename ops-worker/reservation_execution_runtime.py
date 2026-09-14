"""Composition adapter for reservation execution and operational alerts."""

from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple


class ReservationExecutionRuntime:
    """Resolve reservation execution dependencies from a live worker namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def record_reservation_operation(
        self,
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
    ) -> Any:
        get = self._get
        return get("_record_reservation_operation_impl")(
            reservation_id,
            lab_id,
            host_name,
            action,
            status,
            success,
            response_code,
            duration_ms,
            payload,
            message,
            engine=get("DB_ENGINE"),
            now=get("_now_utc"),
            sql_text=get("text"),
            json_dumps=get("json").dumps,
            check_failure_alert=lambda *args, **kwargs: get("_check_failure_alert")(
                *args,
                **kwargs,
            ),
            logger=get("logging"),
            sanitize_log_value=get("_sanitize_log_value"),
        )

    def record_power_operation(self, operation: Dict[str, Any]) -> None:
        get = self._get
        return get("_project_power_operation_impl")(
            operation,
            record_operation=lambda *args, **kwargs: get("record_reservation_operation")(
                *args,
                **kwargs,
            ),
            logger=get("logging"),
        )

    def host_local_mode_enabled(self, host: Dict[str, Any]) -> bool:
        get = self._get
        return get("_host_local_mode_enabled_impl")(
            host,
            db_engine=get("DB_ENGINE"),
            fetch_latest_heartbeat=get("_fetch_latest_heartbeat"),
            parse_bool=get("parse_bool"),
            logger=get("logging"),
        )

    def execute_reservation_power_phase(
        self,
        reservation_id: str,
        lab_id: Optional[str],
        host: Dict[str, Any],
        phase: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        get = self._get
        return get("_execute_reservation_power_phase_impl")(
            reservation_id,
            lab_id,
            host,
            phase,
            payload,
            parse_bool=get("parse_bool"),
            power_runtime=get("POWER_RUNTIME"),
            power_validation_error_type=get("PowerValidationError"),
            host_local_mode=lambda value: get("_host_local_mode_enabled")(value),
            logger=get("logging"),
        )

    def should_send_failure_alert(self, host_name: str) -> bool:
        get = self._get
        return get("_should_send_failure_alert_impl")(
            host_name,
            engine=get("DB_ENGINE"),
            enabled=get("NOTIFICATION_SERVICE_ENABLED"),
            url=get("NOTIFICATION_SERVICE_URL"),
            now=get("_now_utc"),
            failure_threshold=get("OPS_ALERT_FAILURE_THRESHOLD"),
            window_seconds=get("OPS_ALERT_WINDOW_SECONDS"),
            cooldown_seconds=get("OPS_ALERT_COOLDOWN_SECONDS"),
            sql_text=get("text"),
        )

    def send_failure_alert(
        self,
        reservation_id: str,
        lab_id: Optional[str],
        host_name: str,
        failure_reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        get = self._get
        return get("_send_failure_alert_impl")(
            reservation_id,
            lab_id,
            host_name,
            failure_reason,
            details,
            recipients=list(get("NOTIFICATION_SERVICE_RECIPIENTS")),
            url=get("NOTIFICATION_SERVICE_URL"),
            token_header=get("NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER"),
            token=get("NOTIFICATION_SERVICE_ACCESS_TOKEN"),
            retry_attempts=get("NOTIFICATION_SERVICE_RETRY_ATTEMPTS"),
            retry_backoff_seconds=get("NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS"),
            http_post=get("requests").post,
            sleep=get("time").sleep,
            record_operation=get("record_reservation_operation"),
            json_dumps=get("json").dumps,
        )

    def check_failure_alert(
        self,
        host_name: str,
        reservation_id: str,
        lab_id: Optional[str],
        action: str,
        message: Optional[str],
        payload: Optional[Dict[str, Any]],
    ) -> None:
        get = self._get
        return get("_check_failure_alert_impl")(
            host_name,
            reservation_id,
            lab_id,
            action,
            message,
            payload,
            should_send=get("_should_send_failure_alert"),
            failure_threshold=get("OPS_ALERT_FAILURE_THRESHOLD"),
            window_seconds=get("OPS_ALERT_WINDOW_SECONDS"),
            send_failure_alert=get("_send_failure_alert"),
        )

    def notify_critical_failure(
        self,
        reservation_id: str,
        lab_id: Optional[str],
        host_name: str,
        action: str,
        failure_reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        get = self._get
        return get("_notify_critical_failure_impl")(
            reservation_id,
            lab_id,
            host_name,
            action,
            failure_reason,
            details,
            enabled=get("NOTIFICATION_SERVICE_ENABLED"),
            url=get("NOTIFICATION_SERVICE_URL"),
            recipients=list(get("NOTIFICATION_SERVICE_RECIPIENTS")),
            token_header=get("NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER"),
            token=get("NOTIFICATION_SERVICE_ACCESS_TOKEN"),
            retry_attempts=get("NOTIFICATION_SERVICE_RETRY_ATTEMPTS"),
            retry_backoff_seconds=get("NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS"),
            http_post=get("requests").post,
            sleep=get("time").sleep,
            now_seconds=get("time").time,
            record_operation=get("record_reservation_operation"),
            json_dumps=get("json").dumps,
            logger=get("logging"),
            sanitize_log_value=get("_sanitize_log_value"),
        )

    def perform_wake_step(
        self,
        host: Dict[str, Any],
        reservation_id: str,
        lab_id: Optional[str],
        options: Dict[str, Any],
    ) -> Tuple[bool, Dict[str, Any]]:
        get = self._get
        return get("_perform_wake_step_impl")(
            host,
            reservation_id,
            lab_id,
            options,
            wol_and_wait=lambda *args, **kwargs: get("wol_and_wait")(*args, **kwargs),
            record_operation=lambda *args, **kwargs: get("record_reservation_operation")(
                *args,
                **kwargs,
            ),
            notify_failure=lambda *args, **kwargs: get("notify_critical_failure")(
                *args,
                **kwargs,
            ),
            current_epoch=get("time").time,
            logger=get("logging"),
        )

    def perform_command_step(
        self,
        host: Dict[str, Any],
        reservation_id: str,
        lab_id: Optional[str],
        action: str,
        command: str,
        args: List[str],
    ) -> Tuple[bool, Dict[str, Any]]:
        get = self._get
        return get("_perform_command_step_impl")(
            host,
            reservation_id,
            lab_id,
            action,
            command,
            args,
            run_labstation_command=lambda *call_args, **call_kwargs: get(
                "run_labstation_command"
            )(*call_args, **call_kwargs),
            record_operation=lambda *call_args, **call_kwargs: get(
                "record_reservation_operation"
            )(*call_args, **call_kwargs),
            notify_failure=lambda *call_args, **call_kwargs: get("notify_critical_failure")(
                *call_args,
                **call_kwargs,
            ),
            current_epoch=get("time").time,
            logger=get("logging"),
        )


def create_reservation_execution_runtime(
    providers: Mapping[str, Any],
) -> ReservationExecutionRuntime:
    """Create a reservation execution adapter bound to live providers."""
    return ReservationExecutionRuntime(providers)


__all__ = ["ReservationExecutionRuntime", "create_reservation_execution_runtime"]
