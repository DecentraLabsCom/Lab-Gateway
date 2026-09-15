from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from timeline_context import TimelineContext
from timeline_runtime import TimelineRuntime, create_timeline_runtime


def _context(*, calls=None, hosts=None):
    calls = calls if calls is not None else []
    state = {"hosts": hosts or SimpleNamespace(get_by_lab=lambda _lab: "host")}
    context = TimelineContext(
        to_iso_impl=lambda value, **kwargs: calls.append(("iso", value, kwargs)) or "iso",
        get_datetime=lambda: SimpleNamespace(fromisoformat="fromisoformat"),
        get_timezone=lambda: SimpleNamespace(utc="UTC"),
        sanitize_limit_impl=lambda value, **kwargs: calls.append(
            ("limit", value, kwargs)
        ) or 5,
        get_default_limit=lambda: 10,
        get_max_limit=lambda: 20,
        sanitize_offset_impl=lambda value: calls.append(("offset", value)) or 2,
        rows_to_operations_impl=lambda rows, **kwargs: calls.append(
            ("rows", rows, kwargs)
        ) or [{"id": 1}],
        get_to_iso=lambda: lambda value: "iso",
        build_reservation_timeline_impl=lambda *args, **kwargs: calls.append(
            ("timeline", args, kwargs)
        ) or {"reservationId": args[0]},
        get_db_engine=lambda: "db",
        get_host_by_lab=lambda: state["hosts"].get_by_lab,
        get_sql_text=lambda: "sql",
        get_rows_to_operations=lambda: lambda rows: [{"id": 1}],
        get_phase_lookback=lambda: 30,
        get_fetch_latest_heartbeat=lambda: "fetch",
        get_summarize_phases=lambda: "summarize",
        fetch_latest_heartbeat_impl=lambda *args, **kwargs: calls.append(
            ("fetch", args, kwargs)
        ) or None,
        get_json_loads=lambda: "loads",
        summarize_phases_impl=lambda operations: {"count": len(operations)},
    )
    return context, state


def test_timeline_runtime_forwards_normalization_and_projection_dependencies():
    calls = []
    context, _state = _context(calls=calls)
    runtime = create_timeline_runtime(context)

    assert isinstance(runtime, TimelineRuntime)
    assert runtime.to_iso("timestamp") == "iso"
    assert runtime.sanitize_limit(None) == 5
    assert runtime.sanitize_offset(None) == 2
    assert runtime.rows_to_operations([]) == [{"id": 1}]
    assert runtime.build_reservation_timeline("res-1", 5, 0) == {
        "reservationId": "res-1"
    }
    assert runtime.fetch_latest_heartbeat("conn", "host") is None
    assert runtime.summarize_phases([]) == {"count": 0}
    assert any(call[0] == "timeline" for call in calls)


def test_timeline_runtime_resolves_mutable_host_registry_at_call_time():
    first = SimpleNamespace(get_by_lab=lambda _value: "first")
    second = SimpleNamespace(get_by_lab=lambda _value: "second")
    context, state = _context(hosts=first)
    context = replace(
        context,
        build_reservation_timeline_impl=lambda _reservation_id, *args, **kwargs: kwargs[
            "host_by_lab"
        ]("lab"),
        get_db_engine=lambda: None,
    )
    runtime = create_timeline_runtime(context)

    assert runtime.build_reservation_timeline("res", 1, 0) == "first"
    state["hosts"] = second
    assert runtime.build_reservation_timeline("res", 1, 0) == "second"


def test_timeline_context_is_immutable():
    context, _state = _context()

    with pytest.raises(FrozenInstanceError):
        context.get_db_engine = lambda: None
