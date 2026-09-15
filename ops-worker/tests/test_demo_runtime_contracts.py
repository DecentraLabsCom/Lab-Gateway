from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from demo_context import DemoContext
from demo_runtime import DemoRuntime, create_demo_runtime


def _context(*, calls=None, **overrides):
    calls = calls if calls is not None else []
    state = {
        "hosts": SimpleNamespace(get_by_lab=lambda lab_id: {"name": f"host-{lab_id}"}),
        "reservation_start": lambda value: calls.append(("start", value)),
        "reservation_end": lambda value: calls.append(("end", value)),
        "record_event": lambda *args: calls.append(("event", args)),
    }
    captured = {}

    def build_readiness(**kwargs):
        captured["readiness"] = kwargs
        return {"status": "ready"}

    def build_context(*args, **kwargs):
        captured["context"] = (args, kwargs)
        return ({"demo_id": "demo:jti", "lab_id": "7"}, None)

    values = {
        "get_mandatory_field_impl": lambda payload, *keys: calls.append(
            ("mandatory", payload, keys)
        ) or "value",
        "canonical_demo_lab_id_impl": lambda value: calls.append(
            ("lab", value)
        ) or "7",
        "build_demo_readiness_impl": build_readiness,
        "get_demo_lab_id": lambda: "7",
        "get_demo_connection_id": lambda: "9",
        "get_demo_user": lambda: "demo-user",
        "get_demo_heartbeat_max_age": lambda: 30,
        "get_guacamole_db_engine": lambda: "guac-db",
        "get_db_engine": lambda: "ops-db",
        "get_find_host_by_lab": lambda: state["hosts"].get_by_lab,
        "get_fetch_latest_heartbeat": lambda: "fetch-heartbeat",
        "get_to_utc": lambda: "to-utc",
        "get_sql_text": lambda: "sql-text",
        "get_now": lambda: lambda: ("now", "UTC"),
        "get_logger": lambda: "logger",
        "build_demo_context_impl": build_context,
        "get_demo_operation_id_pattern": lambda: "demo-pattern",
        "get_canonical_demo_lab_id": lambda: "canonical",
        "operation_completed_impl": lambda *args, **kwargs: False,
        "record_demo_event_impl": lambda *args, **kwargs: None,
        "get_demo_event_actions": lambda: {"start": "start"},
        "get_record_reservation_operation": lambda: lambda *args, **kwargs: None,
        "demo_host_is_ready_impl": lambda *args, **kwargs: True,
        "handle_demo_start_impl": lambda payload, **kwargs: (
            kwargs["reservation_start"]({"source": "start"}),
            kwargs["reservation_end"]({"source": "end"}),
            kwargs["record_event"]("context", "start", True),
            (payload, 200),
        )[-1],
        "get_demo_context": lambda: lambda payload: ({}, None),
        "get_operation_completed": lambda: lambda *args: False,
        "get_parse_bool": lambda: bool,
        "get_demo_host_is_ready": lambda: lambda _host: True,
        "get_reservation_start": lambda: state["reservation_start"],
        "get_reservation_end": lambda: state["reservation_end"],
        "get_record_demo_event": lambda: state["record_event"],
        "handle_demo_event_impl": lambda payload, **kwargs: (payload, 200),
        "handle_demo_end_impl": lambda payload, **kwargs: (payload, 200),
    }
    values.update(overrides)
    return DemoContext(**values), state, captured, calls


def test_demo_runtime_forwards_readiness_and_context_dependencies():
    context, _state, captured, _calls = _context()
    runtime = create_demo_runtime(context)

    assert isinstance(runtime, DemoRuntime)
    assert runtime.demo_readiness() == {"status": "ready"}
    assert runtime.demo_context({"demoId": "demo:jti", "labId": "7"}) == (
        {"demo_id": "demo:jti", "lab_id": "7"},
        None,
    )
    assert captured["readiness"]["find_host_by_lab"]("7")["name"] == "host-7"
    assert captured["readiness"]["fetch_latest_heartbeat"] == "fetch-heartbeat"
    assert captured["readiness"]["now"]() == ("now", "UTC")
    assert captured["context"][1] == {
        "operation_id_pattern": "demo-pattern",
        "canonical_lab_id": "canonical",
        "configured_lab_id": "7",
        "find_host_by_lab": captured["readiness"]["find_host_by_lab"],
        "db_engine": "ops-db",
    }


def test_demo_runtime_resolves_lifecycle_callbacks_dynamically():
    calls = []
    context, state, _captured, _calls = _context(calls=calls)
    context = replace(
        context,
        handle_demo_start_impl=lambda payload, **kwargs: (
            kwargs["reservation_start"]({"source": "start"}),
            kwargs["reservation_end"]({"source": "end"}),
            kwargs["record_event"]("context", "start", True),
            (payload, 200),
        )[-1],
    )
    runtime = create_demo_runtime(context)
    state["reservation_start"] = lambda payload: calls.append(("start-new", payload))

    runtime.handle_demo_start({"demoId": "demo:jti"})

    assert calls == [
        ("start-new", {"source": "start"}),
        ("end", {"source": "end"}),
        ("event", ("context", "start", True)),
    ]


def test_demo_runtime_forwards_demo_value_helpers():
    context, _state, _captured, calls = _context()
    runtime = create_demo_runtime(context)

    assert runtime.get_mandatory_field({"name": "value"}, "name") == "value"
    assert runtime.canonical_demo_lab_id("007") == "7"
    assert calls == [
        ("mandatory", {"name": "value"}, ("name",)),
        ("lab", "007"),
    ]


def test_demo_context_is_immutable():
    context, _state, _captured, _calls = _context()

    with pytest.raises(FrozenInstanceError):
        context.get_logger = lambda: "changed"
