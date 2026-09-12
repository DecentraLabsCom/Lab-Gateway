"""Heartbeat hint discovery with explicit WinRM and parsing dependencies."""

from collections.abc import Callable
from typing import Any, Dict, List


def discover_heartbeat_hint(
    hostname: str,
    *,
    credentials_configured: Callable[[str], bool],
    path_candidates: Callable[[Dict[str, Any]], List[str]],
    read_remote_file: Callable[..., str],
    parse_json: Callable[[str], Any],
    suggest_mac: Callable[[Dict[str, Any]], Any],
    winrm_port: int,
    logger: Any,
) -> Dict[str, Any]:
    """Discover a readable heartbeat file and its optional MAC hint."""
    if not hostname:
        return {"checked": False, "detected": False, "status": "missing-hostname"}

    temp_host = {
        "name": hostname,
        "address": hostname,
        "credential_ref": hostname,
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": winrm_port,
    }
    if not credentials_configured(hostname):
        return {
            "checked": False,
            "detected": False,
            "status": "missing-winrm-credentials",
        }

    errors = []
    heartbeat = None
    detected_path = None
    for path in path_candidates(temp_host):
        try:
            raw = read_remote_file(
                temp_host,
                path,
                None,
                None,
                None,
                None,
                None,
            )
            heartbeat = parse_json(raw)
            detected_path = path
            break
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Unable to read heartbeat candidate %s: %s", path, exc)
            errors.append({"path": path, "error": "Remote heartbeat read failed"})

    if heartbeat is None:
        return {"checked": True, "detected": False, "status": "read-failed", "errors": errors}

    mac_hint = suggest_mac(heartbeat)
    result = {"checked": True, "detected": True, "path": detected_path}
    if mac_hint:
        result["suggestedMac"] = mac_hint
    return result
