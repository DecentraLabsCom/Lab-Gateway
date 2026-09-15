"""Composition of the mutable Ops Worker service runtimes."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeServices:
    """Runtime objects published through the worker compatibility aliases."""

    power_state: Any
    reservation_automator: Any


def create_runtime_services(
    *,
    power_factory: Callable[..., Any],
    power_arguments: Mapping[str, Any],
    reservation_factory: Callable[..., Any],
    reservation_engine: Any,
    reservation_registry: Any,
) -> RuntimeServices:
    """Build mutable service runtimes in their historical order.

    The factories and arguments are explicit so the composition root can keep
    live callbacks while this module remains independent from Flask and
    module globals.
    """
    power_state = power_factory(**dict(power_arguments))
    reservation_automator = reservation_factory(
        reservation_engine,
        reservation_registry,
    )
    return RuntimeServices(
        power_state=power_state,
        reservation_automator=reservation_automator,
    )


__all__ = ["RuntimeServices", "create_runtime_services"]
