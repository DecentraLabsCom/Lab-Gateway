from concurrent.futures import Future

from execution_tracking import SimulationRegistry


def test_simulation_registry_registers_and_normalizes_claim_context():
    registry = SimulationRegistry()
    future = Future()

    registry.register(
        "sim-1",
        future,
        "42",
        {"reservationKey": "RES-1", "pucHash": "PUC-1"},
    )

    assert registry.get("sim-1") == (
        future,
        "42",
        "res-1",
        "puc-1",
        None,
    )


def test_simulation_registry_pop_removes_entry_and_returns_missing_as_none():
    registry = SimulationRegistry()
    future = Future()
    registry.register("sim-1", future, "42", {})

    assert registry.pop("sim-1") == (future, "42", "", "", None)
    assert registry.get("sim-1") is None
    assert registry.pop("missing") is None


def test_simulation_registry_counts_entries_for_a_lab():
    registry = SimulationRegistry()
    future = Future()
    registry.register("sim-1", future, "42", {})
    registry.register("sim-2", future, "42", {})
    registry.register("sim-3", future, "7", {})

    assert registry.count_for_lab("42") == 2
    assert registry.count_for_lab("missing") == 0
