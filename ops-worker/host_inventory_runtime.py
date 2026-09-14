"""Composition adapter for the public host inventory."""

from collections.abc import Mapping
from typing import Any, Dict


class HostInventoryRuntime:
    """Resolve inventory projection and source coordination from live providers."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def safe_host_inventory_entry(
        self,
        host: Dict[str, Any],
        *,
        editable: bool = False,
    ) -> Dict[str, Any]:
        get = self._get
        return get("_safe_host_inventory_entry_impl")(
            host,
            editable=editable,
            credential_ref_for_host=get("credential_ref_for_host"),
            inspect_winrm_trust=get("inspect_winrm_trust"),
            winrm_credentials_configured=get("winrm_credentials_configured"),
            default_heartbeat_path=r"C:\LabStation\labstation\data\telemetry\heartbeat.json",
        )

    def build_host_inventory(self) -> Dict[str, Any]:
        get = self._get
        return get("_build_host_inventory_from_sources_impl")(
            get("HOSTS"),
            hosts_lock=get("HOSTS_LOCK"),
            load_dynamic_config=get("load_dynamic_config"),
            load_guacamole_connections=get("load_guacamole_connections"),
            normalize_key=get("normalize_match_key"),
            safe_entry=get("safe_host_inventory_entry"),
        )


def create_host_inventory_runtime(providers: Mapping[str, Any]) -> HostInventoryRuntime:
    """Create an inventory adapter bound to live providers."""
    return HostInventoryRuntime(providers)


__all__ = ["HostInventoryRuntime", "create_host_inventory_runtime"]
