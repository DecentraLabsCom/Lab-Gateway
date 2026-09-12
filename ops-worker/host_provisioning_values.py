"""Pure host naming, lab validation and provisioning payload construction."""

from collections.abc import Callable
from typing import Any, Dict, List, Optional, Pattern, Tuple


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


def normalize_labs(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, list):
        parts = value
    else:
        parts = []
    return [str(part).strip() for part in parts if str(part).strip()]


def validate_labs_against_candidates(labs: List[str], candidates: Any) -> Optional[str]:
    if candidates is None:
        return None
    valid = set(normalize_labs(candidates))
    if not valid:
        return "validLabIds must contain at least one lab candidate when provided"
    invalid = [lab for lab in labs if lab not in valid]
    if invalid:
        return f"labs contain values that are not valid candidates: {', '.join(invalid)}"
    return None


def build_provisioned_host(
    payload: Dict[str, Any],
    connection: Dict[str, Any],
    *,
    sanitize_host_name_fn: Callable[[Any, Optional[Any]], Tuple[Optional[str], Optional[str]]],
    normalize_labs_fn: Callable[[Any], List[str]],
    validate_labs_fn: Callable[[List[str], Any], Optional[str]],
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

    labs = normalize_labs_fn(payload.get("labs"))
    labs_error = validate_labs_fn(labs, payload.get("validLabIds"))
    if labs_error:
        return None, labs_error
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
        "labs": labs,
    }
    if mac:
        host_config["mac"] = mac
    return host_config, None
