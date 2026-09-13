from session_observation_state import ObservationState, create_observation_state


def test_observation_state_creates_empty_set_and_lock():
    state = create_observation_state()

    assert isinstance(state, ObservationState)
    assert state.observed_credentials == set()
    assert state.lock is not None


def test_observation_state_accepts_injected_factories_in_set_then_lock_order():
    events = []
    observed = {"existing"}
    lock = object()

    def set_factory():
        events.append("set")
        return observed

    def lock_factory():
        events.append("lock")
        return lock

    state = create_observation_state(
        set_factory=set_factory,
        lock_factory=lock_factory,
    )

    assert state.observed_credentials is observed
    assert state.lock is lock
    assert events == ["set", "lock"]
