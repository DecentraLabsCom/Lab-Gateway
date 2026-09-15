"""Composition adapter for Ops Worker process startup."""

from typing import Any

from entrypoint_context import EntrypointContext


class EntrypointRuntime:
    """Expose process startup through explicit dependencies."""

    def __init__(self, context: EntrypointContext):
        self._context = context

    def configure_logging(self) -> None:
        context = self._context
        return context.get_configure_logging_impl()(
            level=context.get_log_level(),
            basic_config=context.get_basic_config(),
        )

    def main(self) -> Any:
        context = self._context
        return context.get_run_impl()(
            configure_logging=context.get_configure_logging(),
            refresh_trust_store=context.get_refresh_trust_store(),
            hosts=context.get_hosts(),
            start_scheduler=context.get_start_scheduler(),
            bind=context.get_bind(),
            port=context.get_port(),
            serve=context.get_serve(),
            app=context.get_app(),
        )


def create_entrypoint_runtime(context: EntrypointContext) -> EntrypointRuntime:
    """Create an entrypoint runtime bound to explicit providers."""
    return EntrypointRuntime(context)


__all__ = ["EntrypointRuntime", "create_entrypoint_runtime"]
