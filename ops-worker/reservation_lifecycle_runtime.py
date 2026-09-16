"""Composition adapter for reservation lifecycle operations."""

from typing import Any, Dict, Tuple

from reservation_lifecycle_context import ReservationLifecycleContext


class ReservationLifecycleRuntime:
    """Expose reservation start/end handlers through explicit dependency ports."""

    def __init__(self, context: ReservationLifecycleContext):
        self._context = context

    def _find_host(self, host_name: Any) -> Any:
        return self._context.get_hosts().get(host_name)

    def handle_reservation_start(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        return self._context.handle_reservation_start_impl(
            payload,
            find_host=self._find_host,
            resolve_host_by_lab=self._context.get_resolve_host_by_lab(),
            get_mandatory_field=self._context.get_mandatory_field(),
            parse_bool=self._context.get_parse_bool(),
            execute_power_phase=self._context.get_execute_power_phase(),
            perform_wake_step=self._context.get_perform_wake_step(),
            perform_command_step=self._context.get_perform_command_step(),
            normalize_args=self._context.get_normalize_args(),
        )

    def handle_reservation_end(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        return self._context.handle_reservation_end_impl(
            payload,
            find_host=self._find_host,
            resolve_host_by_lab=self._context.get_resolve_host_by_lab(),
            get_mandatory_field=self._context.get_mandatory_field(),
            parse_bool=self._context.get_parse_bool(),
            execute_power_phase=self._context.get_execute_power_phase(),
            perform_command_step=self._context.get_perform_command_step(),
            normalize_args=self._context.get_normalize_args(),
        )


def create_reservation_lifecycle_runtime(
    context: ReservationLifecycleContext,
) -> ReservationLifecycleRuntime:
    """Create a lifecycle adapter bound to explicit ports."""
    return ReservationLifecycleRuntime(context)


__all__ = ["ReservationLifecycleRuntime", "create_reservation_lifecycle_runtime"]
