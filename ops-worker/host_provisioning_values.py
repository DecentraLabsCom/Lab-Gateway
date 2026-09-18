"""Pure host naming and provisioning payload construction."""

from collections.abc import Callable
from typing import Any, Dict, Optional, Pattern, Tuple

from labstation_paths import paths_for_root, resolve_labstation_paths
from runtime_values import (
    DEFAULT_EVENTS_PATH,
    DEFAULT_HEARTBEAT_PATH,
    DEFAULT_LABSTATION_EXE,
    DEFAULT_LOCAL_MODE_FLAG_PATH,
)


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
    default_heartbeat_path: str = DEFAULT_HEARTBEAT_PATH,
    default_events_path: str = DEFAULT_EVENTS_PATH,
    default_labstation_exe: str = DEFAULT_LABSTATION_EXE,
    default_local_mode_flag_path: str = DEFAULT_LOCAL_MODE_FLAG_PATH,
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
    broadcast = str(payload.get("broadcast") or "").strip()
    if broadcast and (len(broadcast) > 64 or any(ord(char) < 32 for char in broadcast)):
        return None, "broadcast must be a valid network address"

    labstation_path = str(payload.get("labstationPath") or "").strip()
    if labstation_path and (len(labstation_path) > 1024 or any(ord(char) < 32 for char in labstation_path)):
        return None, "labstationPath must be a valid Windows path"

    path_config = {
        "labstation_exe": payload.get("labstationExe"),
        "local_mode_flag_path": payload.get("localModeFlagPath"),
        "heartbeat_path": payload.get("heartbeatPath"),
        "events_path": payload.get("eventsPath"),
    }
    if labstation_path:
        station_paths = paths_for_root(labstation_path)
    elif any(path_config.values()):
        station_paths = resolve_labstation_paths(path_config)
    else:
        station_paths = {
            "labstation_exe": default_labstation_exe,
            "local_mode_flag_path": default_local_mode_flag_path,
            "heartbeat_path": default_heartbeat_path,
            "events_path": default_events_path,
        }

    host_config = {
        "name": name,
        "address": address,
        "credential_ref": credential_ref,
        "winrm_trust_ref": normalize_trust_ref_fn(name),
        "winrm_transport": str(payload.get("winrmTransport") or "ntlm").strip() or "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
        **station_paths,
    }
    if mac:
        host_config["mac"] = mac
    if broadcast:
        host_config["broadcast"] = broadcast
    return host_config, None
