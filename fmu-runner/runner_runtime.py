"""Mutable Gateway facade resources shared by the application routes."""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from session_observation_state import ObservationState, create_observation_state


@dataclass
class FmuRunnerRuntime:
    """Own session-observation, proxy-rate-limit and remote-service state."""

    observation: ObservationState
    proxy_download_hits: dict[str, deque[float]]
    proxy_download_lock: Any
    backend: Any = None
    realtime_manager: Any = None
    _backend_bound: bool = field(default=False, init=False, repr=False)
    _realtime_bound: bool = field(default=False, init=False, repr=False)

    @property
    def observed_credentials(self) -> set[str]:
        return self.observation.observed_credentials

    @property
    def observation_lock(self) -> Any:
        return self.observation.lock

    def bind_backend(self, backend: Any) -> None:
        if self._backend_bound:
            raise RuntimeError("FMU backend is already bound")
        self.backend = backend
        self._backend_bound = True

    def bind_realtime_manager(self, manager: Any) -> None:
        if self._realtime_bound:
            raise RuntimeError("Realtime manager is already bound")
        self.realtime_manager = manager
        self._realtime_bound = True


def create_fmu_runner_runtime(
    *,
    observation_set_factory: Any = set,
    lock_factory: Any = Lock,
    proxy_hits_factory: Any = None,
) -> FmuRunnerRuntime:
    """Create runtime state without a local FMU process pool or job registry."""
    observation = create_observation_state(
        set_factory=observation_set_factory,
        lock_factory=lock_factory,
    )
    proxy_download_hits = (
        defaultdict(deque)
        if proxy_hits_factory is None
        else proxy_hits_factory()
    )
    return FmuRunnerRuntime(
        observation=observation,
        proxy_download_hits=proxy_download_hits,
        proxy_download_lock=lock_factory(),
    )


__all__ = ["FmuRunnerRuntime", "create_fmu_runner_runtime"]
