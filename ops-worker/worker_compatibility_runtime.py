"""Compatibility adapters retained by the Ops Worker composition root."""

from collections.abc import Mapping, MutableMapping
from typing import Any


class WorkerCompatibilityRuntime:
    """Keep historical worker helpers while resolving mutable providers lazily."""

    def __init__(self, providers: MutableMapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def is_lite_gateway(self) -> bool:
        return self._get("_is_lite_gateway_config_impl")(self._get("os").environ)

    def now_utc(self) -> Any:
        return self._get("datetime").now(self._get("timezone").utc)

    def winrm_trust_host_or_404(self, host_name: str):
        host = self._get("HOSTS").get(host_name)
        if not host:
            return None, (
                self._get("jsonify")(
                    {"error": f"host '{host_name}' not found in config"}
                ),
                404,
            )
        return host, None

    def set_host_registry(self, registry: Any) -> None:
        self._providers["HOSTS"] = registry

    def replace_host_registry(self, registry: Any) -> None:
        with self._get("HOSTS_LOCK"):
            self._get("_replace_host_registry_impl")(
                registry,
                set_registry=self._get("_set_host_registry"),
                reservation_automator=self._get("RESERVATION_AUTOMATOR"),
            )


def create_worker_compatibility_runtime(
    providers: MutableMapping[str, Any],
) -> WorkerCompatibilityRuntime:
    """Create the compatibility adapter bound to the live worker namespace."""
    return WorkerCompatibilityRuntime(providers)


__all__ = ["WorkerCompatibilityRuntime", "create_worker_compatibility_runtime"]
