from concurrent.futures import Future
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from runner_runtime import create_fmu_runner_runtime


def _runtime():
    return create_fmu_runner_runtime(
        create_executor=lambda: "executor",
        slots_factory=lambda: _Slots(),
        registry_factory=lambda: _Registry(),
        observation_set_factory=set,
        lock_factory=lambda: object(),
        history_db_path="history.db",
    )


class _Slots:
    def __init__(self):
        self.calls = []

    def acquire(self, lab_id, limit):
        self.calls.append(("acquire", lab_id, limit))

    def release(self, lab_id):
        self.calls.append(("release", lab_id))


class _Registry:
    def __init__(self):
        self.entries = {}

    def register(self, sim_id, future, lab_id, claims, executor=None):
        self.entries[sim_id] = (future, lab_id, claims, executor)

    def get(self, sim_id):
        return self.entries.get(sim_id)

    def pop(self, sim_id):
        return self.entries.pop(sim_id, None)


def test_runtime_owns_execution_observation_and_proxy_state():
    runtime = _runtime()
    future = Future()

    assert runtime.executor == "executor"
    assert runtime.backend is None
    assert runtime.realtime_manager is None
    assert runtime.history_db_path == "history.db"
    assert runtime.observed_credentials == set()
    assert runtime.proxy_download_hits == {}

    runtime.acquire_slot("lab-1", 3)
    runtime.release_slot("lab-1")
    runtime.track_running_future("sim-1", future, "lab-1", {"reservationKey": "r"})

    assert runtime.get_running_entry("sim-1")[0] is future
    assert runtime.pop_running_entry("sim-1")[0] is future
    assert runtime.get_running_entry("sim-1") is None
    assert runtime.execution.slots.calls == [
        ("acquire", "lab-1", 3),
        ("release", "lab-1"),
    ]


def test_runtime_binds_backend_and_realtime_once():
    runtime = _runtime()
    backend = object()
    realtime = object()

    runtime.bind_backend(backend)
    runtime.bind_realtime_manager(realtime)

    assert runtime.backend is backend
    assert runtime.realtime_manager is realtime

    with pytest.raises(RuntimeError):
        runtime.bind_backend(object())
    with pytest.raises(RuntimeError):
        runtime.bind_realtime_manager(object())


def test_runtime_allows_explicit_executor_replacement_for_controlled_tests():
    runtime = _runtime()

    runtime.executor = "replacement"

    assert runtime.executor == "replacement"


def test_runtime_state_is_explicit_and_has_no_module_namespace_lookup():
    source = Path(__file__).parents[1].joinpath("runner_runtime.py").read_text(encoding="utf-8")

    assert "globals()" not in source
    assert "Mapping" not in source
