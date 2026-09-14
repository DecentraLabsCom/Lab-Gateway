from types import SimpleNamespace

from demo_runtime import DemoRuntime, create_demo_runtime


def test_demo_runtime_forwards_readiness_and_context_dependencies():
    captured = {}

    def build_readiness(**kwargs):
        captured["readiness"] = kwargs
        return {"status": "ready"}

    def build_context(*args, **kwargs):
        captured["context"] = (args, kwargs)
        return ({"demo_id": "demo:jti", "lab_id": "7"}, None)

    hosts = SimpleNamespace(
        get_by_lab=lambda lab_id: {"name": f"host-{lab_id}"},
    )
    providers = {
        "_build_demo_readiness_impl": build_readiness,
        "DEMO_LAB_ID": "7",
        "DEMO_CONNECTION_ID": "9",
        "DEMO_USER": "demo-user",
        "DEMO_HEARTBEAT_MAX_AGE_SECONDS": 30,
        "GUACAMOLE_DB_ENGINE": "guac-db",
        "DB_ENGINE": "ops-db",
        "HOSTS": hosts,
        "_fetch_latest_heartbeat": "fetch-heartbeat",
        "to_utc": "to-utc",
        "text": "sql-text",
        "datetime": SimpleNamespace(now=lambda timezone: ("now", timezone)),
        "timezone": SimpleNamespace(utc="UTC"),
        "logging": "logger",
        "_build_demo_context_impl": build_context,
        "DEMO_OPERATION_ID_RE": "demo-pattern",
        "_canonical_demo_lab_id": "canonical",
    }
    runtime = create_demo_runtime(providers)

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
        "find_host_by_lab": hosts.get_by_lab,
        "db_engine": "ops-db",
    }


def test_demo_runtime_resolves_lifecycle_callbacks_dynamically():
    calls = []

    def handle_start(payload, **kwargs):
        kwargs["reservation_start"]({"source": "start"})
        kwargs["reservation_end"]({"source": "end"})
        kwargs["record_event"]("context", "start", True)
        return payload, 200

    providers = {
        "_handle_demo_start_impl": handle_start,
        "_demo_context": lambda _payload: ({}, None),
        "_demo_operation_completed": lambda *_args: False,
        "parse_bool": bool,
        "_demo_host_is_ready": lambda _host: True,
        "handle_reservation_start": lambda payload: calls.append(("start", payload)),
        "handle_reservation_end": lambda payload: calls.append(("end", payload)),
        "_record_demo_event": lambda *args: calls.append(("event", args)),
    }
    runtime = create_demo_runtime(providers)
    providers["handle_reservation_start"] = lambda payload: calls.append(("start-new", payload))

    runtime.handle_demo_start({"demoId": "demo:jti"})

    assert calls == [
        ("start-new", {"source": "start"}),
        ("end", {"source": "end"}),
        ("event", ("context", "start", True)),
    ]


def test_demo_runtime_forwards_demo_value_helpers():
    calls = []
    providers = {
        "_get_mandatory_field_impl": lambda payload, *keys: calls.append(
            ("mandatory", payload, keys)
        ) or "value",
        "_canonical_demo_lab_id_impl": lambda value: calls.append(
            ("lab", value)
        ) or "7",
    }
    runtime = create_demo_runtime(providers)

    assert runtime.get_mandatory_field({"name": "value"}, "name") == "value"
    assert runtime.canonical_demo_lab_id("007") == "7"
    assert calls == [("mandatory", {"name": "value"}, ("name",)), ("lab", "007")]
