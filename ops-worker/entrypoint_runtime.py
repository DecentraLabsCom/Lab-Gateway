"""Composition adapter for Ops Worker process startup."""

from collections.abc import Mapping
from typing import Any


class EntrypointRuntime:
    """Resolve process-startup dependencies from a live worker namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def configure_logging(self) -> None:
        get = self._get
        return get("_configure_logging_impl")(
            level=get("os").getenv("OPS_LOG_LEVEL", "INFO"),
            basic_config=get("logging").basicConfig,
        )

    def main(self) -> Any:
        get = self._get
        environ = get("os").getenv
        return get("_run_entrypoint_impl")(
            configure_logging=get("configure_logging"),
            refresh_trust_store=get("refresh_winrm_trust_store"),
            hosts=get("HOSTS").all_hosts(),
            start_scheduler=get("start_scheduler"),
            bind=environ("OPS_BIND", "0.0.0.0"),
            port=int(environ("OPS_PORT", "8081")),
            serve=get("serve"),
            app=get("APP"),
        )


def create_entrypoint_runtime(providers: Mapping[str, Any]) -> EntrypointRuntime:
    """Create a process-startup adapter bound to live providers."""
    return EntrypointRuntime(providers)


__all__ = ["EntrypointRuntime", "create_entrypoint_runtime"]
