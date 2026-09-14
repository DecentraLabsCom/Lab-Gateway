"""Composition adapter for host catalog reloads."""

from collections.abc import Mapping
from typing import Any, Tuple, Optional


class HostReloadRuntime:
    """Resolve catalog reload orchestration from a live worker namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def reload_hosts(self) -> Tuple[int, Optional[str]]:
        get = self._get
        return get("_reload_hosts_impl")(
            load_config=get("load_config"),
            registry_factory=get("HostRegistry"),
            refresh_trust_store=get("refresh_winrm_trust_store"),
            replace_registry=get("_replace_host_registry"),
            logger=get("logging"),
        )


def create_host_reload_runtime(providers: Mapping[str, Any]) -> HostReloadRuntime:
    """Create a host-reload adapter bound to live providers."""
    return HostReloadRuntime(providers)


__all__ = ["HostReloadRuntime", "create_host_reload_runtime"]
