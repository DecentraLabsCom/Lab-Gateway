"""Explicit dependencies for the Ops Worker host inventory boundary."""

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


class HostRegistryProtocol(Protocol):
    """Minimal host registry surface required by the inventory projection."""

    def all_hosts(self) -> Sequence[Dict[str, Any]]:
        ...


@dataclass(frozen=True)
class HostInventoryContext:
    """Dependencies required to build the public host inventory."""

    get_host_registry: Callable[[], HostRegistryProtocol]
    get_hosts_lock: Callable[[], AbstractContextManager[Any]]
    load_dynamic_config: Callable[[], Dict[str, Any]]
    load_guacamole_connections: Callable[
        [], tuple[Sequence[Dict[str, Any]], Optional[str]]
    ]
    normalize_match_key: Callable[[Any], str]
    credential_ref_for_host: Callable[[Dict[str, Any]], str]
    inspect_winrm_trust: Callable[[Dict[str, Any]], Dict[str, Any]]
    winrm_credentials_configured: Callable[[str], bool]
    default_heartbeat_path: str = r"C:\LabStation\labstation\data\telemetry\heartbeat.json"


__all__ = ["HostInventoryContext", "HostRegistryProtocol"]
