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
        end_payload = dict(payload)
        shutdown_ops_optional = False
        if not reconciliation_only and not end_payload.get("powerAction"):
            get_schedule = self._context.get_shutdown_ops_schedule
            if get_schedule is not None:
                lab_id = end_payload.get("labId") or end_payload.get("lab_id")
                host_name = end_payload.get("host") or end_payload.get("hostName")
                host = self._find_host(host_name) if host_name else None
                if not host and lab_id:
                    host = self._context.get_resolve_host_by_lab()(str(lab_id))
                if host:
                    try:
                        schedule = get_schedule()(str(host.get("name") or host_name or ""))
                    except Exception:  # The optional shutdown setting must not block reservation release.
                        schedule = {}
                    if schedule.get("afterReservationEnd") is True:
                        end_payload["powerAction"] = {
                            "mode": "shutdown",
                            "args": [
                                "--delay=0",
                                "--require-idle",
                                "--reason=Reservation ended",
                            ],
                        }
                        shutdown_ops_optional = True
        kwargs = {}
        if authoritative_reservation is not None:
            kwargs["authoritative_reservation"] = authoritative_reservation
        if reconciliation_attempt is not None:
            kwargs["reconciliation_attempt"] = reconciliation_attempt
        if reconciliation_only:
            kwargs["reconciliation_only"] = True
        if shutdown_ops_optional:
            kwargs["shutdown_ops_optional"] = True
        return self._context.handle_reservation_end_impl(
            end_payload,
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
