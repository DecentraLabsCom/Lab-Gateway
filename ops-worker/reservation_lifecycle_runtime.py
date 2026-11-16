"""Composition adapter for reservation lifecycle operations."""

from typing import Any, Dict, Mapping, Optional, Tuple

from reservation_lifecycle_context import ReservationLifecycleContext


class ReservationLifecycleRuntime:
    """Expose reservation start/end handlers through explicit dependency ports."""

    def __init__(self, context: ReservationLifecycleContext):
        self._context = context

    def _find_host(self, host_name: Any) -> Any:
        return self._context.get_hosts().get(host_name)

    def handle_reservation_start(
        self,
        payload: Dict[str, Any],
        *,
        authoritative_reservation: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], int]:
        kwargs = {}
        if authoritative_reservation is not None:
            kwargs["authoritative_reservation"] = authoritative_reservation
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
            resolve_station_lease_context=self._context.get_resolve_station_lease(),
            authorize_remote_session_handoff=(
                self._context.get_authorize_remote_session_handoff()
                if self._context.get_authorize_remote_session_handoff is not None
                else None
            ),
            **kwargs,
        )

    def handle_reservation_end(
        self,
        payload: Dict[str, Any],
        *,
        authoritative_reservation: Optional[Mapping[str, Any]] = None,
        reconciliation_attempt: Optional[str] = None,
        reconciliation_only: bool = False,
    ) -> Tuple[Dict[str, Any], int]:
        kwargs = {}
        if authoritative_reservation is not None:
            kwargs["authoritative_reservation"] = authoritative_reservation
        if reconciliation_attempt is not None:
            kwargs["reconciliation_attempt"] = reconciliation_attempt
        if reconciliation_only:
            kwargs["reconciliation_only"] = True
        return self._context.handle_reservation_end_impl(
            payload,
            find_host=self._find_host,
            resolve_host_by_lab=self._context.get_resolve_host_by_lab(),
            get_mandatory_field=self._context.get_mandatory_field(),
            parse_bool=self._context.get_parse_bool(),
            execute_power_phase=self._context.get_execute_power_phase(),
            perform_command_step=self._context.get_perform_command_step(),
            normalize_args=self._context.get_normalize_args(),
            resolve_station_lease_context=self._context.get_resolve_station_lease(),
            **kwargs,
        )


def create_reservation_lifecycle_runtime(
    context: ReservationLifecycleContext,
) -> ReservationLifecycleRuntime:
    """Create a lifecycle adapter bound to explicit ports."""
    return ReservationLifecycleRuntime(context)


__all__ = ["ReservationLifecycleRuntime", "create_reservation_lifecycle_runtime"]
