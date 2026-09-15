"""Composition adapter for reservation execution and operational alerts."""

from typing import Any, Dict, List, Optional, Tuple

from reservation_execution_context import ReservationExecutionContext


class ReservationExecutionRuntime:
    """Expose reservation execution through explicit persistence and operation ports."""

    def __init__(self, context: ReservationExecutionContext):
        self._context = context

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
        return self._context.record_reservation_operation_impl(
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
            engine=self._context.get_db_engine(),
            now=self._context.get_now_utc(),
            sql_text=self._context.get_sql_text(),
            json_dumps=self._context.get_json_dumps(),
            check_failure_alert=self._context.get_check_failure_alert(),
            logger=self._context.get_logger(),
            sanitize_log_value=self._context.get_sanitize_log_value(),
        )

    def record_power_operation(self, operation: Dict[str, Any]) -> None:
        return self._context.project_power_operation_impl(
            operation,
            record_operation=self._context.get_record_reservation_operation(),
            logger=self._context.get_logger(),
        )

    def host_local_mode_enabled(self, host: Dict[str, Any]) -> bool:
        return self._context.host_local_mode_enabled_impl(
            host,
            db_engine=self._context.get_db_engine(),
            fetch_latest_heartbeat=self._context.get_fetch_latest_heartbeat(),
            parse_bool=self._context.get_parse_bool(),
            logger=self._context.get_logger(),
        )

    def execute_reservation_power_phase(
        self,
        reservation_id: str,
        lab_id: Optional[str],
        host: Dict[str, Any],
        phase: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._context.execute_reservation_power_phase_impl(
            reservation_id,
            lab_id,
            host,
            phase,
            payload,
            parse_bool=self._context.get_parse_bool(),
            power_runtime=self._context.get_power_runtime(),
            power_validation_error_type=self._context.get_power_validation_error_type(),
            host_local_mode=self._context.get_host_local_mode_enabled(),
            logger=self._context.get_logger(),
        )

    def should_send_failure_alert(self, host_name: str) -> bool:
        return self._context.should_send_failure_alert_impl(
            host_name,
            engine=self._context.get_db_engine(),
            enabled=self._context.get_notification_enabled(),
            url=self._context.get_notification_url(),
            now=self._context.get_now_utc(),
            failure_threshold=self._context.get_failure_threshold(),
            window_seconds=self._context.get_window_seconds(),
            cooldown_seconds=self._context.get_cooldown_seconds(),
            sql_text=self._context.get_sql_text(),
        )

    def send_failure_alert(
        self,
        reservation_id: str,
        lab_id: Optional[str],
        host_name: str,
        failure_reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        return self._context.send_failure_alert_impl(
            reservation_id,
            lab_id,
            host_name,
            failure_reason,
            details,
            recipients=list(self._context.get_recipients()),
            url=self._context.get_notification_url(),
            token_header=self._context.get_token_header(),
            token=self._context.get_token(),
            retry_attempts=self._context.get_retry_attempts(),
            retry_backoff_seconds=self._context.get_retry_backoff_seconds(),
            http_post=self._context.get_http_post(),
            sleep=self._context.get_sleep(),
            record_operation=self._context.get_record_reservation_operation(),
            json_dumps=self._context.get_json_dumps(),
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
        return self._context.check_failure_alert_impl(
            host_name,
            reservation_id,
            lab_id,
            action,
            message,
            payload,
            should_send=self._context.get_should_send_failure_alert(),
            failure_threshold=self._context.get_failure_threshold(),
            window_seconds=self._context.get_window_seconds(),
            send_failure_alert=self._context.get_send_failure_alert(),
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
        return self._context.notify_critical_failure_impl(
            reservation_id,
            lab_id,
            host_name,
            action,
            failure_reason,
            details,
            enabled=self._context.get_notification_enabled(),
            url=self._context.get_notification_url(),
            recipients=list(self._context.get_recipients()),
            token_header=self._context.get_token_header(),
            token=self._context.get_token(),
            retry_attempts=self._context.get_retry_attempts(),
            retry_backoff_seconds=self._context.get_retry_backoff_seconds(),
            http_post=self._context.get_http_post(),
            sleep=self._context.get_sleep(),
            now_seconds=self._context.get_current_epoch(),
            record_operation=self._context.get_record_reservation_operation(),
            json_dumps=self._context.get_json_dumps(),
            logger=self._context.get_logger(),
            sanitize_log_value=self._context.get_sanitize_log_value(),
        )

    def perform_wake_step(
        self,
        host: Dict[str, Any],
        reservation_id: str,
        lab_id: Optional[str],
        options: Dict[str, Any],
    ) -> Tuple[bool, Dict[str, Any]]:
        return self._context.perform_wake_step_impl(
            host,
            reservation_id,
            lab_id,
            options,
            wol_and_wait=self._context.get_wol_and_wait(),
            record_operation=self._context.get_record_reservation_operation(),
            notify_failure=self._context.get_notify_critical_failure(),
            current_epoch=self._context.get_current_epoch(),
            logger=self._context.get_logger(),
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
        return self._context.perform_command_step_impl(
            host,
            reservation_id,
            lab_id,
            action,
            command,
            args,
            run_labstation_command=self._context.get_run_labstation_command(),
            record_operation=self._context.get_record_reservation_operation(),
            notify_failure=self._context.get_notify_critical_failure(),
            current_epoch=self._context.get_current_epoch(),
            logger=self._context.get_logger(),
        )


def create_reservation_execution_runtime(
    context: ReservationExecutionContext,
) -> ReservationExecutionRuntime:
    """Create a reservation execution adapter bound to explicit ports."""
    return ReservationExecutionRuntime(context)


__all__ = ["ReservationExecutionRuntime", "create_reservation_execution_runtime"]
