"""Shared Station management settings used by Wake-on-LAN operations."""

from collections.abc import Mapping
import time
from typing import Any, Callable, Optional


DEFAULT_MANAGEMENT_PORTS = {"winrm": 5986, "ssh": 22}


def management_transport(host: Mapping[str, Any]) -> str:
    """Return the configured Station transport, preserving legacy WinRM rows."""
    management_value = host.get("management")
    management = management_value if isinstance(management_value, Mapping) else {}
    return str(
        management.get("transport") or host.get("management_transport") or "winrm"
    ).strip().lower()


def management_port(
    host: Mapping[str, Any], transport: Optional[str] = None
) -> Optional[int]:
    """Return the Station's configured management port, or None if invalid."""
    selected_transport = (transport or management_transport(host)).strip().lower()
    if selected_transport not in DEFAULT_MANAGEMENT_PORTS:
        return None

    management_value = host.get("management")
    management = management_value if isinstance(management_value, Mapping) else {}
    fallback = host.get("management_port")
    if fallback in (None, ""):
        fallback = (
            host.get("winrm_port")
            if selected_transport == "winrm"
            else DEFAULT_MANAGEMENT_PORTS[selected_transport]
        )
    value = management.get("port", fallback)
    if value in (None, ""):
        value = DEFAULT_MANAGEMENT_PORTS[selected_transport]
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def station_identity_matches(host: Mapping[str, Any], result: Any) -> bool:
    """Require a successful authenticated probe over the configured transport."""
    return (
        isinstance(result, Mapping)
        and result.get("reachable") is True
        and str(result.get("transport") or "").strip().lower()
        == management_transport(host)
    )


def wait_for_station_identity(
    host: Mapping[str, Any],
    probe_station: Callable[[Mapping[str, Any]], Any],
    timeout_seconds: float,
) -> bool:
    """Wait briefly for the authenticated Station service after its port opens."""
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    while True:
        try:
            if station_identity_matches(host, probe_station(host)):
                return True
        except Exception:
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(2.0, remaining))


__all__ = [
    "management_port",
    "management_transport",
    "station_identity_matches",
    "wait_for_station_identity",
]
