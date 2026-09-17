"""Composition for the Wake-on-LAN HTTP route."""

from typing import Any, Callable, Dict, Optional, Tuple

from wol_defaults import DEFAULT_WOL_ATTEMPTS, DEFAULT_WOL_PING_TIMEOUT_SECONDS


def handle_wol(
    payload: Any,
    *,
    find_host: Callable[[Any], Optional[Dict[str, Any]]],
    is_valid_ping_target: Callable[[str], bool],
    wol_and_wait: Callable[..., Tuple[bool, int]],
    now: Callable[[], float],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[[str, BaseException], Any],
) -> Any:
    """Validate a WOL request and forward the physical operation."""
    host_name = payload.get("host")
    host = find_host(host_name) if host_name else None
    mac = payload.get("mac") or (host or {}).get("mac")
    if not mac:
        return jsonify({"error": "mac is required"}), 400

    ping_target = str(
        payload.get("ping_target")
        or (host or {}).get("ping_target")
        or (host or {}).get("address")
        or ""
    ).strip()
    if not ping_target:
        return jsonify({"error": "ping_target or host address is required"}), 400
    if not is_valid_ping_target(ping_target):
        return jsonify({"error": "ping_target is invalid"}), 400

    attempts = int(payload.get("attempts", DEFAULT_WOL_ATTEMPTS))
    wait_seconds = float(
        payload.get("ping_timeout", DEFAULT_WOL_PING_TIMEOUT_SECONDS)
    )
    # Prefer the request override, then the host's persisted LAN broadcast.
    # The latter is required for directed broadcasts when the worker runs in
    # a container with more than one network interface.
    broadcast = payload.get("broadcast") or (host or {}).get("broadcast")
    port = int(payload.get("port", 9))
    configured_probe_port = (host or {}).get("winrm_port")
    try:
        probe_port = int(configured_probe_port) if configured_probe_port not in (None, "") else None
    except (TypeError, ValueError):
        probe_port = None

    start = now()
    try:
        up, used_attempts = wol_and_wait(
            mac,
            broadcast,
            port,
            ping_target,
            attempts,
            wait_seconds,
            probe_port=probe_port,
        )
    except Exception as exc:
        return internal_error_response("WOL failed", exc)

    return jsonify({
        "success": up,
        "attempts_used": used_attempts,
        "duration_ms": int((now() - start) * 1000),
        "ping_target": ping_target,
    })


__all__ = ["handle_wol"]
