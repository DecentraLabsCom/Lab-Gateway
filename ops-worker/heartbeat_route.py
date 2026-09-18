"""Composition for the heartbeat polling HTTP route."""

from typing import Any, Callable, Dict, Mapping, Optional, Type

from errors import (
    WINRM_AUTH_FAILED_CODE,
    build_winrm_unreachable_payload,
    build_winrm_heartbeat_error_payload,
    is_winrm_authentication_error,
    is_winrm_unreachable_error,
    WinRMHeartbeatError,
    winrm_heartbeat_error_status,
)


def handle_heartbeat_poll(
    payload: Mapping[str, Any],
    *,
    find_host: Callable[[Any], Optional[Dict[str, Any]]],
    poll_heartbeat: Callable[[Dict[str, Any], bool], Dict[str, Any]],
    now: Callable[[], float],
    jsonify: Callable[[Any], Any],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    request_id: Callable[[], str],
    missing_credentials_predicate: Callable[[ValueError], bool],
    credentials_required_message: str,
    internal_error_response: Callable[[str, BaseException], Any],
) -> Any:
    """Handle heartbeat polling while leaving Flask registration in the root."""
    host_name = payload.get("host")
    include_events = bool(payload.get("include_events", True))
    if not host_name:
        return jsonify({"error": "host is required"}), 400
    host = find_host(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404
    start = now()
    try:
        data = poll_heartbeat(host, include_events)
        data["duration_ms"] = int((now() - start) * 1000)
        data["host"] = host_name
        return jsonify(data)
    except trust_error_type as exc:
        error_code = str(getattr(exc, "code", ""))
        return jsonify(trust_error_payload(host_name, error_code)), 409
    except WinRMHeartbeatError as exc:
        error_code = str(getattr(exc, "code", ""))
        return (
            jsonify(
                build_winrm_heartbeat_error_payload(
                    host_name,
                    error_code,
                    request_id=request_id,
                )
            ),
            winrm_heartbeat_error_status(error_code),
        )
    except ValueError as exc:
        if missing_credentials_predicate(exc):
            return jsonify({
                "error": credentials_required_message,
                "code": "WINRM_CREDENTIALS_REQUIRED",
                "host": host_name,
            }), 409
        return internal_error_response("Heartbeat poll failed", exc)
    except Exception as exc:
        if is_winrm_authentication_error(exc):
            return (
                jsonify(
                    build_winrm_heartbeat_error_payload(
                        host_name,
                        WINRM_AUTH_FAILED_CODE,
                        request_id=request_id,
                    )
                ),
                winrm_heartbeat_error_status(WINRM_AUTH_FAILED_CODE),
            )
        if is_winrm_unreachable_error(exc):
            return jsonify(build_winrm_unreachable_payload(host_name, host)), 503
        return internal_error_response("Heartbeat poll failed", exc)


__all__ = ["handle_heartbeat_poll"]
