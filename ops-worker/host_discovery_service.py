"""Lab Station host discovery orchestration with explicit dependencies."""

from collections.abc import Callable, Sequence
from typing import Any, Dict

from labstation_paths import resolve_labstation_paths


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
    ssh_port: int = 22,
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
                "ssh": {},
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
    ssh_checks = {str(ssh_port): tcp_probe(host, ssh_port, discovery_timeout)}
    secure_winrm_reachable = winrm_checks[str(winrm_port)]
    ssh_reachable = ssh_checks[str(ssh_port)]
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
    elif ssh_reachable:
        # An open SSH port is only a provisioning hint. Authentication and the
        # station identity handshake still require a generated key and pinned
        # server host key.
        status = "management-trust-pending"
    elif labstation_http.get("detected") is True:
        status = "labstation-detected-without-winrm"
    elif dns_ok:
        status = "host-resolves"
    else:
        status = "no-response"

    if ssh_reachable and not secure_winrm_reachable:
        ops_host_draft = {
            "name": connection.get("hostname"),
            "address": connection.get("hostname"),
            "platform": "linux",
            "contract": {"major": 3},
            "profile": "dedicated",
            "management_transport": "ssh",
            "management_port": ssh_port,
            "management": {
                "transport": "ssh", "port": ssh_port,
                "credentialRef": connection.get("hostname"),
                "trustRef": connection.get("hostname"),
            },
            "station": {"command": "/usr/bin/labstationctl"},
            "artifacts": {"heartbeat": "heartbeat", "events": "session-events"},
            "nameCandidates": name_candidates(connection),
        }
    else:
        heartbeat_path = heartbeat.get("path") or heartbeat_paths[0]
        station_paths = resolve_labstation_paths({"heartbeat_path": heartbeat_path})
        if heartbeat.get("path"):
            events_path = station_paths["events_path"]
        ops_host_draft = {
            "name": connection.get("hostname"),
            "address": connection.get("hostname"),
            "winrm_transport": "ntlm",
            "winrm_use_ssl": True,
            "winrm_port": draft_winrm_port,
            "labstation_exe": station_paths["labstation_exe"],
            "local_mode_flag_path": station_paths["local_mode_flag_path"],
            "heartbeat_path": station_paths["heartbeat_path"],
            "events_path": events_path,
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
            "ssh": ssh_checks,
            "managementPortReachable": bool(secure_winrm_reachable or ssh_reachable),
            "managementTrustPending": bool(ssh_reachable and not secure_winrm_reachable),
            "labStationHttp": labstation_http,
            "heartbeat": heartbeat,
        },
        "opsHostDraft": ops_host_draft,
    }
