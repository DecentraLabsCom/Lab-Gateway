from unittest.mock import MagicMock

from execution_state import ExecutionState, create_execution_state


def test_execution_state_creates_slots_executor_and_registry_in_order():
    events = []
    slots = object()
    executor = object()
    registry = object()

    def slots_factory():
        events.append("slots")
        return slots

    def create_executor():
        events.append("executor")
        return executor

    def registry_factory():
        events.append("registry")
        return registry

    state = create_execution_state(
        create_executor=create_executor,
        slots_factory=slots_factory,
        registry_factory=registry_factory,
    )

    assert isinstance(state, ExecutionState)
    assert state.slots is slots
    assert state.executor is executor
    assert state.registry is registry
    assert events == ["slots", "executor", "registry"]


def test_execution_state_defaults_to_production_factories():
    create_executor = MagicMock(return_value="executor")

    state = create_execution_state(create_executor=create_executor)

    assert state.executor == "executor"
    assert state.slots is not None
    assert state.registry is not None
    create_executor.assert_called_once_with()
