"""Persistence boundary for reservation operation timeline entries."""

from collections.abc import Callable, Mapping
from typing import Any, Dict, Optional


def _safe_log_value(value: Any) -> str:
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


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
    *,
    engine: Any,
    now: Callable[[], Any],
    sql_text: Callable[[str], Any],
    json_dumps: Callable[[Any], str],
    check_failure_alert: Callable[
        [str, str, Optional[str], str, Optional[str], Optional[Mapping[str, Any]]], Any
    ],
    logger: Any,
    sanitize_log_value: Callable[[Any], str] = _safe_log_value,
) -> None:
    """Insert one operation and trigger alert evaluation for ordinary failures."""
    if not engine:
        return

    created_at = now()
    try:
        with engine.begin() as conn:
            conn.execute(
                sql_text(
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
                    "payload": json_dumps(payload) if payload is not None else None,
                    "message": message,
                    "created_at": created_at,
                },
            )
        if not success and action not in ("notification", "alert"):
            try:
                check_failure_alert(host_name, reservation_id, lab_id, action, message, payload)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "Failure alert check failed for %s: %s",
                    sanitize_log_value(host_name),
                    type(exc).__name__,
                )
    except Exception as exc:  # pylint: disable=broad-except
        logger.error(
            "Failed to persist reservation operation %s/%s: %s",
            sanitize_log_value(reservation_id),
            sanitize_log_value(action),
            type(exc).__name__,
        )


__all__ = ["record_reservation_operation"]
