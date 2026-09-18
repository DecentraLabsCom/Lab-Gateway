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
) -> Dict[str, Any]:
    """Return only the host fields intended for inventory API responses."""
    credential_ref = credential_ref_for_host(host)
    trust = inspect_winrm_trust(host)
    paths = resolve_labstation_paths(host)
    if not host.get("heartbeat_path"):
        paths["heartbeat_path"] = default_heartbeat_path
    station_root = root_from_executable(paths["labstation_exe"]) or root_from_heartbeat(
        paths["heartbeat_path"]
    )
    return {
        "name": host.get("name"),
        "address": host.get("address"),
        "credentialRef": credential_ref,
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
        "winrmConfigured": bool(host.get("winrm_user") and host.get("winrm_pass")) or winrm_credentials_configured(credential_ref),
    }
