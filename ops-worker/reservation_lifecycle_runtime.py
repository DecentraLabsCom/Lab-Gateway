"""Composition adapter for reservation lifecycle operations."""

from collections.abc import Mapping
from typing import Any, Dict, Tuple


class ReservationLifecycleRuntime:
    """Resolve reservation start/end handlers from live worker providers."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def _find_host(self, host_name: Any) -> Any:
        return self._get("HOSTS").get(host_name)

    def handle_reservation_start(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        get = self._get
        return get("_handle_reservation_start_impl")(
            payload,
            find_host=self._find_host,
            get_mandatory_field=get("_get_mandatory_field"),
            parse_bool=get("parse_bool"),
            execute_power_phase=lambda *args: get("_execute_reservation_power_phase")(*args),
            perform_wake_step=lambda *args: get("perform_wake_step")(*args),
            perform_command_step=lambda *args: get("perform_command_step")(*args),
            normalize_args=get("normalize_args"),
        )

    def handle_reservation_end(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        get = self._get
        return get("_handle_reservation_end_impl")(
            payload,
            find_host=self._find_host,
            get_mandatory_field=get("_get_mandatory_field"),
            parse_bool=get("parse_bool"),
            execute_power_phase=lambda *args: get("_execute_reservation_power_phase")(*args),
            perform_command_step=lambda *args: get("perform_command_step")(*args),
            normalize_args=get("normalize_args"),
        )


def create_reservation_lifecycle_runtime(
    providers: Mapping[str, Any],
) -> ReservationLifecycleRuntime:
    """Create a lifecycle adapter bound to live providers."""
    return ReservationLifecycleRuntime(providers)


__all__ = ["ReservationLifecycleRuntime", "create_reservation_lifecycle_runtime"]
