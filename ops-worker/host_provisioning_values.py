"""Pure host naming and provisioning payload construction."""

from collections.abc import Callable
from typing import Any, Dict, Optional, Pattern, Tuple


def sanitize_host_name(
    value: Any,
    fallback: Optional[Any],
    *,
    name_pattern: Pattern[str],
) -> Tuple[Optional[str], Optional[str]]:
    name = str(value or fallback or "").strip()
    if not name_pattern.fullmatch(name):
        return None, "name must contain only letters, numbers, dots, underscores, and hyphens"
    return name, None


def build_provisioned_host(
    payload: Dict[str, Any],
    connection: Dict[str, Any],
    *,
    sanitize_host_name_fn: Callable[[Any, Optional[Any]], Tuple[Optional[str], Optional[str]]],
    normalize_mac_fn: Callable[[Any], str],
    normalize_trust_ref_fn: Callable[[Any], str],
    default_heartbeat_path: str,
    default_events_path: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    fallback_name = connection.get("hostname") or connection.get("name")
    name, error = sanitize_host_name_fn(payload.get("name"), fallback_name)
    if error or name is None:
        return None, error or "host name is required"
    address = str(payload.get("address") or connection.get("hostname") or "").strip()
    if not address:
        return None, "address is required"

    credential_ref = str(payload.get("credentialRef") or address).strip()
    raw_mac = str(payload.get("mac") or "").strip()
    mac = normalize_mac_fn(raw_mac) if raw_mac else ""
    if raw_mac and not mac:
        return None, "mac must use format 00:11:22:33:44:55 or 00-11-22-33-44-55"

    host_config = {
        "name": name,
        "address": address,
        "credential_ref": credential_ref,
        "winrm_trust_ref": normalize_trust_ref_fn(name),
        "winrm_transport": str(payload.get("winrmTransport") or "ntlm").strip() or "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
        "heartbeat_path": str(payload.get("heartbeatPath") or default_heartbeat_path),
        "events_path": str(payload.get("eventsPath") or default_events_path),
    }
    if mac:
        host_config["mac"] = mac
    return host_config, None
