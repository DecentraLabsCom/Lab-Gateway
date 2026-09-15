"""Mutable FMU Runner resources shared by the application routes."""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Optional

from execution_slots import ConcurrencySlots
from execution_state import ExecutionState, create_execution_state
from execution_tracking import SimulationRegistry
from session_observation_state import ObservationState, create_observation_state


@dataclass
class FmuRunnerRuntime:
    """Own the process-wide resources for one FMU Runner application."""

    execution: ExecutionState
    observation: ObservationState
    proxy_download_hits: dict[str, deque[float]]
    proxy_download_lock: Any
    history_db_path: Optional[str] = None
    backend: Any = None
    realtime_manager: Any = None
    _backend_bound: bool = field(default=False, init=False, repr=False)
    _realtime_bound: bool = field(default=False, init=False, repr=False)

    @property
    def slots(self) -> Any:
        return self.execution.slots

    @property
    def executor(self) -> Any:
        return self.execution.executor

    @executor.setter
    def executor(self, value: Any) -> None:
        self.execution.executor = value

    @property
    def registry(self) -> Any:
        return self.execution.registry

    @property
    def observed_credentials(self) -> set[str]:
        return self.observation.observed_credentials

    @property
    def observation_lock(self) -> Any:
        return self.observation.lock

    def acquire_slot(self, lab_id: str, limit: int) -> None:
        self.slots.acquire(lab_id, limit)

    def release_slot(self, lab_id: str) -> None:
        self.slots.release(lab_id)

    def track_running_future(
        self,
        sim_id: str,
        future: Any,
        lab_id: str,
        claims: dict,
        executor: Optional[Any] = None,
    ) -> None:
        self.registry.register(sim_id, future, lab_id, claims, executor)

    def get_running_entry(self, sim_id: str) -> Any:
        return self.registry.get(sim_id)

    def pop_running_entry(self, sim_id: str) -> Any:
        return self.registry.pop(sim_id)

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
    create_executor: Any,
    slots_factory: Any = ConcurrencySlots,
    registry_factory: Any = SimulationRegistry,
    observation_set_factory: Any = set,
    lock_factory: Any = Lock,
    proxy_hits_factory: Any = None,
    history_db_path: Optional[str] = None,
) -> FmuRunnerRuntime:
    """Create all mutable application resources through explicit factories."""
    execution = create_execution_state(
        create_executor=create_executor,
        slots_factory=slots_factory,
        registry_factory=registry_factory,
    )
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
        execution=execution,
        observation=observation,
        proxy_download_hits=proxy_download_hits,
        proxy_download_lock=lock_factory(),
        history_db_path=history_db_path,
    )


__all__ = ["FmuRunnerRuntime", "create_fmu_runner_runtime"]
