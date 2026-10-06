"""Safe public projection of an Ops Worker host entry."""

from collections.abc import Callable
from typing import Any, Dict

from labstation_paths import resolve_labstation_paths, root_from_executable, root_from_heartbeat

def safe_host_inventory_entry(
    host: Dict[str, Any],
    *,
    editable: bool = False,
    credential_ref_for_host: Callable[[Dict[str, Any]], str],
    inspect_winrm_trust: Callable[[Dict[str, Any]], Dict[str, Any]],
    winrm_credentials_configured: Callable[[str], bool],
    default_heartbeat_path: str,
    station_credentials_configured: Callable[[str, str], bool] = lambda _ref, _transport: False,
    inspect_ssh_trust: Callable[[Dict[str, Any]], Dict[str, Any]] = lambda _host: {"status": "missing", "configured": False},
) -> Dict[str, Any]:
    """Return only the host fields intended for inventory API responses."""
    credential_ref = credential_ref_for_host(host)
    management = host.get("management") if isinstance(host.get("management"), dict) else {}
    transport = str(management.get("transport") or host.get("management_transport") or "winrm").lower()
    platform = str(host.get("platform") or ("linux" if transport == "ssh" else "windows")).lower()
    contract = host.get("contract") if isinstance(host.get("contract"), dict) else {}
    if transport == "ssh":
        trust = inspect_ssh_trust(host)
        paths = {"labstation_exe": None, "local_mode_flag_path": None,
                 "heartbeat_path": "heartbeat", "events_path": "session-events"}
        station_root = None
        configured = station_credentials_configured(credential_ref, transport)
        trust_ref = management.get("trustRef") or host.get("ssh_trust_ref") or host.get("name")
        trust_projection = {
            "ref": trust_ref,
            "status": trust.get("status", "missing"),
            "configured": trust.get("status") == "ready",
            "algorithm": trust.get("algorithm"),
            "fingerprintSha256": trust.get("fingerprint"),
        }
    else:
        trust = inspect_winrm_trust(host)
        paths = resolve_labstation_paths(host)
        if not host.get("heartbeat_path"):
            paths["heartbeat_path"] = default_heartbeat_path
        station_root = root_from_executable(paths["labstation_exe"]) or root_from_heartbeat(
            paths["heartbeat_path"]
        )
        configured = bool(host.get("winrm_user") and host.get("winrm_pass")) or winrm_credentials_configured(credential_ref)
        trust_ref = trust.get("trustRef")
        trust_projection = {
            "ref": trust_ref,
            "status": trust.get("status"),
            "configured": trust.get("configured", False),
            "fingerprintSha256": trust.get("fingerprintSha256"),
        }
    return {
        "name": host.get("name"),
        "address": host.get("address"),
        "credentialRef": credential_ref,
        "platform": platform,
        "contractVersion": f"{contract.get('major')}.x" if contract.get("major") else ("3.x" if transport == "ssh" else "2.x"),
        "managementTransport": transport,
        "managementPort": management.get("port") or host.get("management_port") or (22 if transport == "ssh" else host.get("winrm_port", 5986)),
        "profile": host.get("profile"),
        "managementCredentials": {"configured": configured, "credentialRef": credential_ref, "type": "ssh-ed25519" if transport == "ssh" else "winrm-password"},
        "managementTrust": trust_projection,
        "stationCommand": (host.get("station") or {}).get("command") if transport == "ssh" else None,
        "winrmTrustRef": trust.get("trustRef"),
        "winrmTrustConfigured": trust.get("configured", False),
        "winrmTrustStatus": trust.get("status"),
        "winrmTrustErrorCode": trust.get("errorCode"),
        "winrmTrustFingerprintSha256": trust.get("fingerprintSha256"),
        "winrmTrustFingerprintSha1": trust.get("fingerprintSha1"),
        "winrmTrustSubject": trust.get("subject"),
        "winrmTrustSanDnsNames": trust.get("sanDnsNames", []),
        "winrmTrustSanIpAddresses": trust.get("sanIpAddresses", []),
        "winrmTrustNotBefore": trust.get("notBefore"),
        "winrmTrustNotAfter": trust.get("notAfter"),
        "winrmTrustSelfSigned": trust.get("selfSigned"),
        "winrmTrustUploadedAt": trust.get("uploadedAt"),
        "winrmTrustUploadedBy": trust.get("uploadedBy"),
        "winrmTrustSource": trust.get("source"),
        "winrmTrustLastValidatedAt": trust.get("lastValidatedAt"),
        "mac": host.get("mac"),
        "broadcast": host.get("broadcast"),
        "labstationPath": str(station_root) if station_root else None,
        "labstationExe": paths["labstation_exe"],
        "localModeFlagPath": paths["local_mode_flag_path"],
        "heartbeatPath": paths["heartbeat_path"] or default_heartbeat_path,
        "eventsPath": paths["events_path"],
        "mode": host.get("mode"),
        "editable": editable,
        "winrmConfigured": configured if transport == "winrm" else False,
    }
