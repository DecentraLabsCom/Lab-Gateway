"""Lab Station host discovery orchestration with explicit dependencies."""

from collections.abc import Callable, Sequence
from typing import Any, Dict, Optional


def discover_labstation_candidate(
    connection: Dict[str, Any],
    *,
    normalize_host: Callable[[Any], str],
    resolve_dns: Callable[..., Any],
    tcp_probe: Callable[..., bool],
    http_probe: Callable[[str], Dict[str, Any]],
    heartbeat_hint: Callable[[str], Dict[str, Any]],
    name_candidates: Callable[[Dict[str, Any]], list],
    winrm_port: int,
    discovery_timeout: float,
    heartbeat_paths: Sequence[str],
    draft_winrm_port: int,
    events_path: str,
) -> Dict[str, Any]:
    """Combine discovery signals while preserving the public candidate shape."""
    host = normalize_host(connection.get("hostname"))
    if not host:
        return {
            "connection": connection,
            "status": "missing-hostname",
            "checks": {
                "dns": False,
                "winrm": {},
                "labStationHttp": {
                    "checked": False,
                    "detected": False,
                    "status": "missing-hostname",
                },
            },
        }

    try:
        resolve_dns(host, None)
        dns_ok = True
    except OSError:
        dns_ok = False

    winrm_checks = {
        str(winrm_port): tcp_probe(host, winrm_port, discovery_timeout)
    }
    secure_winrm_reachable = winrm_checks[str(winrm_port)]
    labstation_http = http_probe(host)
    heartbeat = (
        heartbeat_hint(host)
        if any(winrm_checks.values())
        else {
            "checked": False,
            "detected": False,
            "status": "winrm-unreachable",
        }
    )
    mac_hint = labstation_http.get("suggestedMac") or heartbeat.get("suggestedMac")

    if labstation_http.get("detected") is True and secure_winrm_reachable:
        status = "labstation-detected"
    elif secure_winrm_reachable:
        status = "winrm-reachable"
    elif labstation_http.get("detected") is True:
        status = "labstation-detected-without-winrm"
    elif dns_ok:
        status = "host-resolves"
    else:
        status = "no-response"

    ops_host_draft = {
        "name": connection.get("hostname"),
        "address": connection.get("hostname"),
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": draft_winrm_port,
        "heartbeat_path": heartbeat.get("path") or heartbeat_paths[0],
        "events_path": events_path,
        "labs": [],
        "nameCandidates": name_candidates(connection),
    }
    if mac_hint:
        ops_host_draft["mac"] = mac_hint["mac"]

    return {
        "connection": connection,
        "status": status,
        "checks": {
            "dns": dns_ok,
            "winrm": winrm_checks,
            "labStationHttp": labstation_http,
            "heartbeat": heartbeat,
        },
        "opsHostDraft": ops_host_draft,
    }
