"""Pure validation of the configured WinRM host catalog."""

import ipaddress
from collections.abc import Callable, Sequence
from typing import Any, Dict, List, Pattern


def validate_winrm_catalog(
    config: Dict[str, Any],
    *,
    management_cidrs: Sequence[str],
    winrm_port: int,
    catalog_bool: Callable[[Any], bool],
    resolve_addresses: Callable[[str], List[Any]],
    trust_ref_pattern: Pattern[str],
) -> None:
    """Reject an invalid Station catalog before it becomes operational."""
    hosts = config.get("hosts", [])
    if not hosts:
        return
    if not management_cidrs:
        raise ValueError("WINRM_MANAGEMENT_CIDRS is required when hosts are configured")
    try:
        management_networks = [ipaddress.ip_network(value, strict=False) for value in management_cidrs]
    except ValueError as exc:
        raise ValueError("WINRM_MANAGEMENT_CIDRS contains an invalid network") from exc

    for host in hosts:
        if not isinstance(host, dict):
            raise ValueError("every catalog host must be an object")
        name = str(host.get("name") or "").strip()
        address = str(host.get("address") or "").strip()
        if not name or not address:
            raise ValueError("every catalog host requires name and address")
        trust_ref = str(host.get("winrm_trust_ref") or "").strip().lower()
        if trust_ref and not trust_ref_pattern.fullmatch(trust_ref):
            raise ValueError(f"host '{name}' has an invalid winrm_trust_ref")
        if "winrm_use_ssl" not in host or "winrm_port" not in host:
            raise ValueError(f"host '{name}' must declare winrm_use_ssl and winrm_port")
        if not catalog_bool(host.get("winrm_use_ssl")):
            raise ValueError(f"host '{name}' must use WinRM HTTPS")
        configured_port = host.get("winrm_port")
        if configured_port not in (None, ""):
            try:
                configured_port = int(configured_port)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"host '{name}' has an invalid winrm_port") from exc
            if configured_port != winrm_port:
                raise ValueError(f"host '{name}' must use WinRM port {winrm_port}")
        addresses = resolve_addresses(address)
        if not any(any(candidate in network for network in management_networks) for candidate in addresses):
            raise ValueError(f"host '{name}' is outside WINRM_MANAGEMENT_CIDRS")
