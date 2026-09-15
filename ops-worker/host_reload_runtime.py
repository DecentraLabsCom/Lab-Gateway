"""Composition adapter for host catalog reloads."""

from typing import Optional, Tuple

from host_reload_context import HostReloadContext


class HostReloadRuntime:
    """Expose catalog reload orchestration through explicit dependencies."""

    def __init__(self, context: HostReloadContext):
        self._context = context

    def reload_hosts(self) -> Tuple[int, Optional[str]]:
        context = self._context
        return context.reload_hosts(
            load_config=context.load_config,
            registry_factory=context.registry_factory,
            refresh_trust_store=context.refresh_trust_store,
            replace_registry=context.replace_registry,
            logger=context.get_logger(),
        )


def create_host_reload_runtime(context: HostReloadContext) -> HostReloadRuntime:
    """Create a host-reload runtime bound to explicit dependencies."""
    return HostReloadRuntime(context)


__all__ = ["HostReloadRuntime", "create_host_reload_runtime"]
