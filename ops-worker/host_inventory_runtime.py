"""Composition adapter for the public host inventory."""

from collections.abc import Callable
from typing import Any, Dict, Optional

from host_inventory_context import HostInventoryContext
from host_inventory_service import build_host_inventory_from_sources
from host_inventory_values import safe_host_inventory_entry


class HostInventoryRuntime:
    """Coordinate inventory projection and source loading from explicit inputs."""

    def __init__(self, context: HostInventoryContext):
        self._context = context

    def safe_host_inventory_entry(
        self,
        host: Dict[str, Any],
        *,
        editable: bool = False,
    ) -> Dict[str, Any]:
        context = self._context
        return safe_host_inventory_entry(
            host,
            editable=editable,
            credential_ref_for_host=context.credential_ref_for_host,
            inspect_winrm_trust=context.inspect_winrm_trust,
            winrm_credentials_configured=context.winrm_credentials_configured,
            default_heartbeat_path=context.default_heartbeat_path,
        )

    def build_host_inventory(
        self,
        *,
        safe_entry: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build inventory using the current source snapshot and projection."""
        context = self._context
        return build_host_inventory_from_sources(
            context.get_host_registry(),
            hosts_lock=context.get_hosts_lock(),
            load_dynamic_config=context.load_dynamic_config,
            load_guacamole_connections=context.load_guacamole_connections,
            normalize_key=context.normalize_match_key,
            safe_entry=(
                safe_entry
                if safe_entry is not None
                else self.safe_host_inventory_entry
            ),
        )

def create_host_inventory_runtime(context: HostInventoryContext) -> HostInventoryRuntime:
    """Create an inventory adapter bound to explicit dependencies."""
    return HostInventoryRuntime(context)


__all__ = ["HostInventoryRuntime", "create_host_inventory_runtime"]
