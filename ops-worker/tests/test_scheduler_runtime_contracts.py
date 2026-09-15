from dataclasses import FrozenInstanceError

import pytest

from scheduler_context import SchedulerContext
from scheduler_runtime import SchedulerRuntime, create_scheduler_runtime


def _context(**overrides):
    values = {
        "get_start_scheduler": lambda: lambda **kwargs: None,
        "get_scheduler_factory": lambda: lambda: "scheduler",
        "get_poll_enabled": lambda: True,
        "get_poll_interval_seconds": lambda: 45,
        "get_poll_all_hosts": lambda: "poll",
        "get_register_reservation_jobs": lambda: "register",
        "get_cleanup_enabled": lambda: True,
        "get_cleanup_interval_seconds": lambda: 900,
        "get_cleanup_expired_users": lambda: "cleanup",
        "get_observation_enabled": lambda: True,
        "get_observation_interval_seconds": lambda: 5,
        "get_deliver_observations": lambda: "observations",
        "get_revocation_interval_seconds": lambda: 10,
        "get_process_revocations": lambda: "revocations",
        "get_now": lambda: lambda: "now",
        "get_logger": lambda: "logger",
    }
    values.update(overrides)
    return SchedulerContext(**values)


def test_scheduler_runtime_forwards_explicit_configuration_and_callbacks():
    calls = []
    context = _context(get_start_scheduler=lambda: lambda **kwargs: calls.append(kwargs))
    runtime = create_scheduler_runtime(context)

    assert isinstance(runtime, SchedulerRuntime)
    assert runtime.start_scheduler() is None
    received = calls[0]
    assert callable(received["scheduler_factory"])
    assert callable(received["now"])
    assert {
        key: value
        for key, value in received.items()
        if key not in {"scheduler_factory", "now"}
    } == {
        "poll_enabled": True,
        "poll_interval_seconds": 45,
        "poll_all_hosts": "poll",
        "register_reservation_jobs": "register",
        "cleanup_enabled": True,
        "cleanup_interval_seconds": 900,
        "cleanup_expired_users": "cleanup",
        "observation_enabled": True,
        "observation_interval_seconds": 5,
        "deliver_observations": "observations",
        "revocation_interval_seconds": 10,
        "process_revocations": "revocations",
        "logger": "logger",
    }


def test_scheduler_runtime_resolves_mutable_configuration_at_call_time():
    poll_enabled = False
    calls = []
    context = _context(
        get_poll_enabled=lambda: poll_enabled,
        get_start_scheduler=lambda: lambda **kwargs: calls.append(kwargs),
    )
    runtime = create_scheduler_runtime(context)
    poll_enabled = True

    assert runtime.start_scheduler() is None
    assert calls[0]["poll_enabled"] is True


def test_scheduler_context_is_immutable():
    context = _context()

    with pytest.raises(FrozenInstanceError):
        context.get_logger = lambda: "changed"
