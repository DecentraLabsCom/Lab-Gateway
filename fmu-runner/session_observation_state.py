"""Mutable state used to deduplicate durable browser observations."""

from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class ObservationState:
    """Credential keys already observed and the lock protecting that set."""

    observed_credentials: set[str]
    lock: Any


def create_observation_state(
    *,
    set_factory: Any = set,
    lock_factory: Any = Lock,
) -> ObservationState:
    """Create an empty observation cache and its synchronization lock."""
    observed_credentials = set_factory()
    lock = lock_factory()
    return ObservationState(observed_credentials=observed_credentials, lock=lock)


__all__ = ["ObservationState", "create_observation_state"]
