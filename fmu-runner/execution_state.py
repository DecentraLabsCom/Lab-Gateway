"""Composition of the mutable execution resources used by FMU Runner."""

from dataclasses import dataclass
from typing import Any

from execution_slots import ConcurrencySlots
from execution_tracking import SimulationRegistry


@dataclass
class ExecutionState:
    """Resources shared by local simulation and cancellation callbacks."""

    slots: Any
    executor: Any
    registry: Any


def create_execution_state(
    *,
    create_executor: Any,
    slots_factory: Any = ConcurrencySlots,
    registry_factory: Any = SimulationRegistry,
) -> ExecutionState:
    """Create execution resources in the historical initialization order."""
    slots = slots_factory()
    executor = create_executor()
    registry = registry_factory()
    return ExecutionState(slots=slots, executor=executor, registry=registry)


__all__ = ["ExecutionState", "create_execution_state"]
