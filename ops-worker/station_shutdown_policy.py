"""Shared shutdown guard policy for all Station platforms and transports."""

from collections.abc import Mapping
from typing import Any, Optional, Tuple


def inspect_shutdown_status(payload: Any) -> Tuple[Optional[bool], str]:
    """Return safe/blocked/unknown and a reason from a fresh status payload."""
    if not isinstance(payload, Mapping):
        return None, "Station status is invalid; shutdown was not sent"

    status_value = payload.get("status")
    status = status_value if isinstance(status_value, Mapping) else payload
    capabilities = status.get("managementCapabilities")
    platform_value = status.get("platform")
    platform = platform_value if isinstance(platform_value, Mapping) else {}
    platform_capabilities = platform.get("capabilities")
    identity_value = status.get("identity")
    identity = identity_value if isinstance(identity_value, Mapping) else {}
    identity_capabilities = identity.get("capabilities")
    advertised = {
        str(value)
        for values in (capabilities, platform_capabilities, identity_capabilities)
        if isinstance(values, list)
        for value in values
    }
    if "power-idle-guard-v1" not in advertised:
        return None, "Station agent lacks guarded shutdown support; update Lab Station before shutdown"

    local_mode = status.get("localModeEnabled")
    if local_mode is True:
        return False, "Station local mode is enabled; shutdown was not sent"
    if local_mode is not False:
        return None, "Station local mode is unknown; shutdown was not sent"

    sessions_value = status.get("sessions")
    sessions = sessions_value if isinstance(sessions_value, Mapping) else {}
    active_sessions = sessions.get("active")
    if sessions.get("queryOk") is not True or not isinstance(active_sessions, list):
        return None, "Station session inventory is unavailable; shutdown was not sent"
    for session in active_sessions:
        if not isinstance(session, Mapping) or type(session.get("active")) is not bool:
            return None, "Station session inventory is invalid; shutdown was not sent"
        if session["active"] and session.get("kind") not in {"management", "service"}:
            return False, "Station has an active user session; shutdown was not sent"
    return True, ""


def shutdown_preflight_error(payload: Any) -> Optional[str]:
    """Return a human-readable block reason unless current state is safe."""
    safe, reason = inspect_shutdown_status(payload)
    return None if safe is True else reason


__all__ = ["inspect_shutdown_status", "shutdown_preflight_error"]
