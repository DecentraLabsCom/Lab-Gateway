from dataclasses import FrozenInstanceError, replace

import pytest

from reservation_lifecycle_context import ReservationLifecycleContext
from reservation_lifecycle_runtime import (
    ReservationLifecycleRuntime,
    create_reservation_lifecycle_runtime,
)


def _context(*, hosts=None, calls=None):
    hosts = hosts if hosts is not None else {"station": {"name": "station"}}
    calls = calls if calls is not None else []
    context = ReservationLifecycleContext(
        handle_reservation_start_impl=lambda payload, **kwargs: calls.append(
            ("start", payload, kwargs)
        ) or ({"action": "start"}, 200),
        handle_reservation_end_impl=lambda payload, **kwargs: calls.append(
            ("end", payload, kwargs)
        ) or ({"action": "end"}, 200),
        get_hosts=lambda: hosts,
        get_resolve_host_by_lab=lambda: lambda _lab_id: {"name": "station"},
        get_mandatory_field=lambda: lambda payload, *keys: "value",
        get_parse_bool=lambda: lambda value, default=True: bool(value),
        get_execute_power_phase=lambda: lambda *args: ("power", args),
        get_perform_wake_step=lambda: lambda *args: ("wake", args),
        get_perform_command_step=lambda: lambda *args: ("command", args),
        get_normalize_args=lambda: lambda value, default=None: list(
            value or default or []
        ),
    )
    return context, hosts, calls


def test_reservation_lifecycle_runtime_forwards_start_and_end_callbacks():
    context, _hosts, calls = _context()
    runtime = create_reservation_lifecycle_runtime(context)

    assert isinstance(runtime, ReservationLifecycleRuntime)
    assert runtime.handle_reservation_start({"id": "start"}) == (
        {"action": "start"},
        200,
    )
    assert runtime.handle_reservation_end({"id": "end"}) == ({"action": "end"}, 200)
    assert [call[0] for call in calls] == ["start", "end"]
    assert calls[0][2]["find_host"]("station") == {"name": "station"}
    assert calls[1][2]["find_host"]("station") == {"name": "station"}


def test_reservation_lifecycle_runtime_resolves_mutable_host_at_call_time():
    hosts = {"station": "first"}
    context, _hosts, _calls = _context(
        hosts=hosts,
    )
    context = replace(
        context,
        handle_reservation_start_impl=lambda payload, **kwargs: kwargs[
            "find_host"
        ]("station"),
    )
    runtime = create_reservation_lifecycle_runtime(context)

    assert runtime.handle_reservation_start({}) == "first"
    hosts["station"] = "second"
    assert runtime.handle_reservation_start({}) == "second"


def test_reservation_lifecycle_context_is_immutable():
    context, _hosts, _calls = _context()

    with pytest.raises(FrozenInstanceError):
        context.get_parse_bool = lambda: bool
