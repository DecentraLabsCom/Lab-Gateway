"""Notification delivery and repeated-failure alert policy."""

from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Any, Dict, Mapping, Optional


def _safe_log_value(value: Any) -> str:
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def should_send_failure_alert(
    host_name: str,
    *,
    engine: Any,
    enabled: bool,
    url: str,
    now: Callable[[], Any],
    failure_threshold: int,
    window_seconds: int,
    cooldown_seconds: int,
    sql_text: Callable[[str], Any],
) -> bool:
    """Check whether a host crossed the failure threshold and has no cooldown alert."""
    if not engine or not host_name:
        return False
    if not enabled or not url:
        return False

    current = now()
    window_start = current - timedelta(seconds=window_seconds)
    cooldown_start = current - timedelta(seconds=cooldown_seconds)

    with engine.begin() as conn:
        failure_count = conn.execute(
            sql_text(
                "SELECT COUNT(*) FROM reservation_operations "
                "WHERE host = :host AND success = 0 "
                "AND action NOT IN ('notification', 'alert') "
                "AND created_at >= :window_start"
            ),
            {"host": host_name, "window_start": window_start},
        ).scalar() or 0

        recent_alert = conn.execute(
            sql_text(
                "SELECT 1 FROM reservation_operations "
                "WHERE host = :host AND action = 'alert' "
                "AND created_at >= :cooldown_start LIMIT 1"
            ),
            {"host": host_name, "cooldown_start": cooldown_start},
        ).scalar()

    return failure_count >= failure_threshold and recent_alert is None


def _build_payload(
    subject: str,
    body: Sequence[str],
    recipients: Sequence[str],
) -> Dict[str, Any]:
    return {
        "recipients": list(recipients),
        "subject": subject,
        "textBody": "\n".join(body),
        "htmlBody": "<p>" + "</p><p>".join(body) + "</p>",
        "icsContent": None,
        "icsFileName": None,
    }


def _build_headers(token_header: str, token: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers[token_header] = token
    return headers


def send_failure_alert(
    reservation_id: str,
    lab_id: Optional[str],
    host_name: str,
    failure_reason: str,
    details: Optional[Dict[str, Any]] = None,
    *,
    recipients: Sequence[str],
    url: str,
    token_header: str,
    token: str,
    retry_attempts: int,
    retry_backoff_seconds: int,
    http_post: Callable[..., Any],
    sleep: Callable[[float], Any],
    record_operation: Callable[..., Any],
    json_dumps: Callable[..., str],
) -> None:
    """Deliver a repeated-failure alert and persist its result."""
    subject = f"Lab Gateway alert: repeated failures for {host_name}"
    body = [
        f"Reservation: {reservation_id}",
        f"Lab ID: {lab_id or 'unknown'}",
        f"Host: {host_name}",
        f"Condition: {failure_reason}",
    ]
    if details:
        body.append(f"Details: {json_dumps(details, default=str)}")

    payload = _build_payload(subject, body, recipients)
    headers = _build_headers(token_header, token)

    attempt = 0
    response = None
    resp_text = None
    status_code = None
    last_exception: Optional[Exception] = None
    while attempt <= retry_attempts:
        attempt += 1
        try:
            response = http_post(url, json=payload, headers=headers, timeout=10)
            status_code = response.status_code
            resp_text = response.text
            success = response.ok
            if success:
                break
            if attempt > retry_attempts:
                break
            sleep(retry_backoff_seconds * attempt)
        except Exception as exc:  # pylint: disable=broad-except
            last_exception = exc
            if attempt > retry_attempts:
                break
            sleep(retry_backoff_seconds * attempt)

    if response is not None and response.ok:
        record_operation(
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
        record_operation(
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


def check_failure_alert(
    host_name: str,
    reservation_id: str,
    lab_id: Optional[str],
    action: str,
    message: Optional[str],
    payload: Optional[Dict[str, Any]],
    *,
    should_send: Callable[[str], bool],
    failure_threshold: int,
    window_seconds: int,
    send_failure_alert: Callable[..., Any],
) -> None:
    if not should_send(host_name):
        return

    failure_reason = (
        f"At least {failure_threshold} failed operations in the last {window_seconds} seconds"
    )
    details = {
        "triggerAction": action,
        "triggerMessage": message,
        "payload": payload,
    }
    send_failure_alert(reservation_id, lab_id, host_name, failure_reason, details)


def notify_critical_failure(
    reservation_id: str,
    lab_id: Optional[str],
    host_name: str,
    action: str,
    failure_reason: str,
    details: Optional[Dict[str, Any]] = None,
    *,
    enabled: bool,
    url: str,
    recipients: Sequence[str],
    token_header: str,
    token: str,
    retry_attempts: int,
    retry_backoff_seconds: int,
    http_post: Callable[..., Any],
    sleep: Callable[[float], Any],
    now_seconds: Callable[[], float],
    record_operation: Callable[..., Any],
    json_dumps: Callable[..., str],
    logger: Any,
    sanitize_log_value: Callable[[Any], str] = _safe_log_value,
) -> None:
    """Deliver an operational failure notification and persist its result."""
    if not enabled or not url:
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
        body.append(f"Details: {json_dumps(details, default=str)}")

    payload = _build_payload(subject, body, recipients)
    headers = _build_headers(token_header, token)

    attempt = 0
    duration_ms = 0
    response = None
    resp_text = None
    status_code = None
    last_exception: Optional[Exception] = None
    while attempt <= retry_attempts:
        attempt += 1
        start = now_seconds()
        try:
            response = http_post(url, json=payload, headers=headers, timeout=10)
            status_code = response.status_code
            resp_text = response.text
            success = response.ok
            duration_ms = int((now_seconds() - start) * 1000)
            if success:
                break
            if attempt > retry_attempts:
                break
            sleep(retry_backoff_seconds * attempt)
        except Exception as exc:  # pylint: disable=broad-except
            last_exception = exc
            duration_ms = int((now_seconds() - start) * 1000)
            if attempt > retry_attempts:
                break
            sleep(retry_backoff_seconds * attempt)

    if response is not None and response.ok:
        record_operation(
            reservation_id,
            lab_id,
            host_name,
            "notification",
            "completed",
            True,
            response_code=status_code,
            duration_ms=duration_ms,
            payload={
                "failureAction": action,
                "notificationUrl": url,
                "attempts": attempt,
                "response": resp_text,
            },
            message=f"Notification sent after {attempt} attempt(s)",
        )
    else:
        error_details = {
            "failureAction": action,
            "notificationUrl": url,
            "attempts": attempt,
            "response": "Notification service did not accept the request",
        }
        if last_exception is not None:
            logger.warning(
                "Notification delivery failed for %s/%s: %s",
                sanitize_log_value(reservation_id),
                sanitize_log_value(action),
                type(last_exception).__name__,
            )
        record_operation(
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


__all__ = [
    "check_failure_alert",
    "notify_critical_failure",
    "send_failure_alert",
    "should_send_failure_alert",
]
