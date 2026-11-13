"""Composition for the Wake-on-LAN HTTP route."""

import math
from collections.abc import Mapping
from typing import Any, Callable, Dict, Optional, Tuple

from station_wake import management_port, management_transport
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
    verify_station: Optional[Callable[[Mapping[str, Any]], bool]] = None,
) -> Any:
    """Validate a WOL request and forward the physical operation."""
    host_name = payload.get("host")
    host = find_host(host_name) if host_name else None
    if host_name and host is None:
        return jsonify({"error": "host was not found"}), 404
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

    try:
        attempts = int(
            payload.get(
                "attempts",
                (host or {}).get("wake_attempts", DEFAULT_WOL_ATTEMPTS),
            )
        )
        wait_seconds = float(
            payload.get("ping_timeout", DEFAULT_WOL_PING_TIMEOUT_SECONDS)
        )
        port = int(payload.get("port", (host or {}).get("wol_port", 9)))
    except (TypeError, ValueError):
        return jsonify({"error": "attempts, ping_timeout, and port must be numeric"}), 400
    if (
        attempts < 1
        or not 1 <= port <= 65535
        or not math.isfinite(wait_seconds)
        or wait_seconds < 0
    ):
        return jsonify({"error": "attempts, ping_timeout, or port is out of range"}), 400
    # Prefer the request override, then the host's persisted LAN broadcast.
    # The latter is required for directed broadcasts when the worker runs in
    # a container with more than one network interface.
    broadcast = payload.get("broadcast") or (host or {}).get("broadcast")
    transport = management_transport(host) if host else None
    if host and transport not in {"winrm", "ssh"}:
        return jsonify({"error": "host management transport is unsupported"}), 400
    probe_port = management_port(host, transport) if host else None
    if host and probe_port is None:
        return jsonify({"error": "host management port is invalid"}), 400

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
        if up and host and verify_station is not None:
            up = bool(verify_station(host))
    except Exception as exc:
        return internal_error_response("WOL failed", exc)

    return jsonify({
        "success": up,
        "attempts_used": used_attempts,
        "duration_ms": int((now() - start) * 1000),
        "ping_target": ping_target,
    })


__all__ = ["handle_wol"]
