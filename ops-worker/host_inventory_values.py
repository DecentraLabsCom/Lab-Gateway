"""Safe public projection of an Ops Worker host entry."""

from collections.abc import Callable
from typing import Any, Dict


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
        "heartbeatPath": host.get("heartbeat_path", default_heartbeat_path),
        "mode": host.get("mode"),
        "editable": editable,
        "winrmConfigured": bool(host.get("winrm_user") and host.get("winrm_pass")) or winrm_credentials_configured(credential_ref),
    }
