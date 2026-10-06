"""Pure validation of the configured WinRM host catalog."""

import ipaddress
import socket
from collections.abc import Callable, Sequence
from typing import Any, Dict, List, Pattern


def catalog_bool(value: Any) -> bool:
    """Parse the catalog's required HTTPS boolean with its historical default."""
    if value is None or value == "":
        return True
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes", "on"):
        return True
    if normalized in ("false", "0", "no", "off"):
        return False
    raise ValueError("winrm_use_ssl must be a boolean")


def resolve_addresses(
    address: str,
    *,
    ip_address: Callable[[str], Any] = ipaddress.ip_address,
    getaddrinfo: Callable[..., Sequence[Any]] = socket.getaddrinfo,
) -> List[Any]:
    """Resolve a literal or hostname into unique IP address objects."""
    try:
        return [ip_address(address)]
    except ValueError:
        try:
            infos = getaddrinfo(address, None, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError(f"address '{address}' cannot be resolved") from exc
        resolved = {ip_address(info[4][0]) for info in infos}
        if not resolved:
            raise ValueError(f"address '{address}' cannot be resolved")
        return list(resolved)


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
    if any(
        isinstance(host, dict)
        and (host.get("management") or str(host.get("management_transport") or "").lower() == "ssh")
        for host in hosts
    ):
        validate_station_catalog(
            config,
            management_cidrs=management_cidrs,
            winrm_port=winrm_port,
            catalog_bool=catalog_bool,
            resolve_addresses=resolve_addresses,
            trust_ref_pattern=trust_ref_pattern,
        )
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


def normalize_station_host(host: Dict[str, Any]) -> Dict[str, Any]:
    """Map old Windows rows and catalog-v2 rows to common management fields."""
    result = dict(host)
    raw_management = result.get("management")
    if isinstance(raw_management, dict):
        management = dict(raw_management)
        transport = str(management.get("transport") or "").strip().lower()
    else:
        transport = str(result.get("management_transport") or "winrm").strip().lower()
        management = {
            "transport": transport,
            "port": result.get("winrm_port", 5986) if transport == "winrm" else result.get("management_port", 22),
            "credentialRef": result.get("credential_ref") or result.get("address") or result.get("name"),
            "trustRef": result.get("ssh_trust_ref" if transport == "ssh" else "winrm_trust_ref") or result.get("name") or result.get("address"),
        }
    if transport not in {"winrm", "ssh"}:
        raise ValueError("management.transport must be winrm or ssh")
    try:
        port = int(management.get("port") or (5986 if transport == "winrm" else 22))
    except (TypeError, ValueError) as exc:
        raise ValueError("management.port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("management.port must be between 1 and 65535")
    management.update({
        "transport": transport,
        "port": port,
        "credentialRef": str(management.get("credentialRef") or result.get("credential_ref") or result.get("address") or result.get("name") or "").strip(),
        "trustRef": str(management.get("trustRef") or result.get("name") or result.get("address") or "").strip().lower(),
    })
    if transport == "ssh":
        if result.get("platform", "linux") != "linux":
            raise ValueError("SSH-managed stations must declare platform linux")
        result.setdefault("platform", "linux")
        result.setdefault("contract", {"major": 3})
        station = dict(result.get("station") or {})
        station.setdefault("command", result.get("station_command") or "/usr/bin/labstationctl")
        result["station"] = station
        artifacts = dict(result.get("artifacts") or {})
        artifacts.setdefault("heartbeat", "heartbeat")
        artifacts.setdefault("events", "session-events")
        result["artifacts"] = artifacts
        result["ssh_trust_ref"] = management["trustRef"]
    else:
        result.setdefault("platform", "windows")
        if not result.get("winrm_use_ssl", True):
            raise ValueError("WinRM stations must use HTTPS")
    result["management"] = management
    result["management_transport"] = transport
    result["management_port"] = port
    result["credential_ref"] = management["credentialRef"]
    return result


def validate_station_catalog(
    config: Dict[str, Any],
    *,
    management_cidrs: Sequence[str],
    winrm_port: int,
    catalog_bool: Callable[[Any], bool],
    resolve_addresses: Callable[[str], List[Any]],
    trust_ref_pattern: Pattern[str],
) -> None:
    """Validate transport-neutral stations and retain strict Windows v2 rules."""
    hosts = config.get("hosts", [])
    if not hosts:
        return
    if not management_cidrs:
        raise ValueError("STATION_MANAGEMENT_CIDRS is required when hosts are configured")
    try:
        networks = [ipaddress.ip_network(value, strict=False) for value in management_cidrs]
    except ValueError as exc:
        raise ValueError("STATION_MANAGEMENT_CIDRS contains an invalid network") from exc
    for raw_host in hosts:
        if not isinstance(raw_host, dict):
            raise ValueError("every catalog host must be an object")
        host = normalize_station_host(raw_host)
        name = str(host.get("name") or "").strip()
        address = str(host.get("address") or "").strip()
        if not name or not address:
            raise ValueError("every catalog host requires name and address")
        if not any(any(candidate in network for network in networks) for candidate in resolve_addresses(address)):
            raise ValueError(f"host '{name}' is outside STATION_MANAGEMENT_CIDRS")
        management = host["management"]
        if not trust_ref_pattern.fullmatch(management["trustRef"]):
            raise ValueError(f"host '{name}' has an invalid management trustRef")
        if management["transport"] == "winrm":
            # Reuse the established Windows HTTPS/certificate validation path.
            legacy = dict(raw_host)
            legacy.pop("management", None)
            legacy.pop("management_transport", None)
            legacy.setdefault("winrm_use_ssl", True)
            legacy["winrm_port"] = management["port"]
            legacy["winrm_trust_ref"] = management["trustRef"]
            validate_winrm_catalog(
                {"hosts": [legacy]},
                management_cidrs=management_cidrs,
                winrm_port=winrm_port,
                catalog_bool=catalog_bool,
                resolve_addresses=resolve_addresses,
                trust_ref_pattern=trust_ref_pattern,
            )
            continue
        contract = host.get("contract")
        if not isinstance(contract, dict) or int(contract.get("major") or 0) != 3:
            raise ValueError(f"host '{name}' must declare Station Contract major 3")
        station = host.get("station") or {}
        command = str(station.get("command") or "")
        if not command.startswith("/") or any(char in command for char in "\r\n\x00"):
            raise ValueError(f"host '{name}' has an invalid station command")
        artifacts = host.get("artifacts") or {}
        if artifacts.get("heartbeat") != "heartbeat" or artifacts.get("events") != "session-events":
            raise ValueError(f"host '{name}' must use logical station artifact identifiers")


__all__ = ["catalog_bool", "resolve_addresses", "validate_winrm_catalog", "validate_station_catalog", "normalize_station_host"]
