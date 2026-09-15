"""Compatibility adapters retained by the Ops Worker composition root."""

from typing import Any

from worker_compatibility_context import WorkerCompatibilityContext


class WorkerCompatibilityRuntime:
    """Keep historical worker helpers behind explicit dependency ports."""

    def __init__(self, context: WorkerCompatibilityContext):
        self._context = context

    def is_lite_gateway(self) -> bool:
        return self._context.get_is_lite_gateway_impl()(self._context.get_environ())

    def now_utc(self) -> Any:
        return self._context.get_datetime().now(self._context.get_timezone().utc)

    def winrm_trust_host_or_404(self, host_name: str):
        host = self._context.get_hosts().get(host_name)
        if not host:
            return None, (
                self._context.get_jsonify()(
                    {"error": f"host '{host_name}' not found in config"}
                ),
                404,
            )
        return host, None

    def set_host_registry(self, registry: Any) -> None:
        self._context.set_host_registry(registry)

    def replace_host_registry(self, registry: Any) -> None:
        with self._context.get_hosts_lock():
            self._context.get_replace_host_registry_impl()(
                registry,
                set_registry=self.set_host_registry,
                reservation_automator=self._context.get_reservation_automator(),
            )


def create_worker_compatibility_runtime(
    context: WorkerCompatibilityContext,
) -> WorkerCompatibilityRuntime:
    """Create the compatibility adapter bound to explicit ports."""
    return WorkerCompatibilityRuntime(context)


__all__ = ["WorkerCompatibilityRuntime", "create_worker_compatibility_runtime"]
