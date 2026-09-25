"""Heartbeat Server-Sent Events stream with explicit dependencies."""

import json
from collections.abc import Callable, Iterator, Mapping
from typing import Any, Dict, Type

from errors import (
    WINRM_AUTH_FAILED_CODE,
    build_winrm_heartbeat_error_payload,
    build_winrm_unreachable_payload,
    is_winrm_authentication_error,
    is_winrm_unreachable_error,
    WinRMHeartbeatError,
)


def format_sse_event(event: str, data: str) -> str:
    """Serialize one event using the gateway's stable SSE framing."""
    return f"event: {event}\ndata: {data}\n\n"


def generate_heartbeat_stream(
    host: Mapping[str, Any],
    include_events: bool,
    *,
    poll_heartbeat: Callable[..., Dict[str, Any]],
    format_sse_event: Callable[[str, str], str],
    trust_error_type: Type[BaseException],
    missing_credentials_predicate: Callable[[BaseException], bool],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    request_id: Callable[[], str],
    logger: Any,
    sanitize_log_value: Callable[[Any], str],
    credentials_required_message: str,
    heartbeat_interval_seconds: float,
    sleep: Callable[[float], None],
) -> Iterator[str]:
    """Yield heartbeat events, retrying transient station reachability failures."""
    while True:
        try:
            data = poll_heartbeat(host, include_events=include_events)
            data["host"] = host.get("name")
            yield format_sse_event("heartbeat", json.dumps(data))
        except trust_error_type as exc:
            error_code = str(getattr(exc, "code", ""))
            logger.info(
                "Heartbeat stream paused for %s: %s",
                sanitize_log_value(host.get("name")),
                error_code,
            )
            yield format_sse_event(
                "error",
                json.dumps(trust_error_payload(host.get("name"), error_code)),
            )
            return
        except WinRMHeartbeatError as exc:
            error_code = str(getattr(exc, "code", ""))
            logger.info(
                "Heartbeat stream paused for %s: %s",
                sanitize_log_value(host.get("name")),
                error_code,
            )
            yield format_sse_event(
                "error",
                json.dumps(
                    build_winrm_heartbeat_error_payload(
                        host.get("name"),
                        error_code,
                        request_id=request_id,
                    )
                ),
            )
            return
        except ValueError as exc:
            if missing_credentials_predicate(exc):
                logger.info(
                    "Heartbeat stream paused for %s: WinRM credentials are required",
                    sanitize_log_value(host.get("name")),
                )
                yield format_sse_event(
                    "error",
                    json.dumps({
                        "error": credentials_required_message,
                        "code": "WINRM_CREDENTIALS_REQUIRED",
                        "host": host.get("name"),
                    }),
                )
                return
            request_id_value = request_id()
            logger.exception(
                "Heartbeat stream failed request_id=%s",
                str(request_id_value).replace("\r", "\\r").replace("\n", "\\n"),
            )
            yield format_sse_event(
                "error",
                json.dumps({
                    "error": "Internal server error",
                    "code": "INTERNAL_ERROR",
                    "requestId": request_id_value,
                    "host": host.get("name"),
                }),
            )
        except Exception as exc:
            if is_winrm_authentication_error(exc):
                logger.info(
                    "Heartbeat stream paused for %s: %s",
                    sanitize_log_value(host.get("name")),
                    WINRM_AUTH_FAILED_CODE,
                )
                yield format_sse_event(
                    "error",
                    json.dumps(
                        build_winrm_heartbeat_error_payload(
                            host.get("name"),
                            WINRM_AUTH_FAILED_CODE,
                            request_id=request_id,
                        )
                    ),
                )
                return
            if is_winrm_unreachable_error(exc):
                logger.info(
                    "Heartbeat stream unavailable for %s: WinRM unreachable",
                    sanitize_log_value(host.get("name")),
                )
                yield format_sse_event(
                    "error",
                    json.dumps(build_winrm_unreachable_payload(host.get("name"), host)),
                )
                # Keep the SSE connection alive. EventSource would otherwise
                # reconnect immediately after every transient WinRM failure,
                # bypassing the configured heartbeat interval.
                sleep(heartbeat_interval_seconds)
                continue
            request_id_value = request_id()
            logger.exception(
                "Heartbeat stream failed request_id=%s",
                str(request_id_value).replace("\r", "\\r").replace("\n", "\\n"),
            )
            yield format_sse_event(
                "error",
                json.dumps({
                    "error": "Internal server error",
                    "code": "INTERNAL_ERROR",
                    "requestId": request_id_value,
                    "host": host.get("name"),
                }),
            )
        sleep(heartbeat_interval_seconds)
