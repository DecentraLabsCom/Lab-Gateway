from types import SimpleNamespace

from timeline_runtime import TimelineRuntime, create_timeline_runtime


def test_timeline_runtime_forwards_normalization_and_projection_dependencies():
    calls = []
    providers = {
        "_to_iso_impl": lambda value, **kwargs: calls.append(("iso", value, kwargs)) or "iso",
        "datetime": SimpleNamespace(fromisoformat="fromisoformat"),
        "timezone": SimpleNamespace(utc="UTC"),
        "_sanitize_limit_impl": lambda value, **kwargs: calls.append(("limit", value, kwargs)) or 5,
        "TIMELINE_DEFAULT_LIMIT": 10,
        "TIMELINE_MAX_LIMIT": 20,
        "_sanitize_offset_impl": lambda value: calls.append(("offset", value)) or 2,
        "_rows_to_operations_impl": lambda rows, **kwargs: calls.append(("rows", rows, kwargs)) or [{"id": 1}],
        "_build_reservation_timeline_impl": lambda *args, **kwargs: calls.append(
            ("timeline", args, kwargs)
        ) or {"reservationId": args[0]},
        "DB_ENGINE": "db",
        "HOSTS": SimpleNamespace(get_by_lab="by-lab"),
        "text": "sql",
        "rows_to_operations": lambda rows: [{"id": 1}],
        "_rows_to_operations": lambda rows: [{"id": 1}],
        "to_iso": lambda value: "iso",
        "_to_iso": lambda value: "iso",
        "TIMELINE_PHASE_LOOKBACK": 30,
        "_fetch_latest_heartbeat": "fetch",
        "_summarize_phases": "summarize",
        "_fetch_latest_heartbeat_impl": lambda *args, **kwargs: calls.append(("fetch", args, kwargs)) or None,
        "json": SimpleNamespace(loads="loads"),
        "_summarize_phases_impl": lambda operations: {"count": len(operations)},
    }
    runtime = create_timeline_runtime(providers)

    assert isinstance(runtime, TimelineRuntime)
    assert runtime.to_iso("timestamp") == "iso"
    assert runtime.sanitize_limit(None) == 5
    assert runtime.sanitize_offset(None) == 2
    assert runtime.rows_to_operations([]) == [{"id": 1}]
    assert runtime.build_reservation_timeline("res-1", 5, 0) == {"reservationId": "res-1"}
    assert runtime.fetch_latest_heartbeat("conn", "host") is None
    assert runtime.summarize_phases([]) == {"count": 0}
    assert any(call[0] == "timeline" for call in calls)


def test_timeline_runtime_resolves_mutable_host_registry_and_callbacks():
    providers = {
        "_build_reservation_timeline_impl": lambda reservation_id, *args, **kwargs: kwargs[
            "host_by_lab"
        ]("lab"),
        "DB_ENGINE": None,
        "HOSTS": SimpleNamespace(get_by_lab=lambda value: "first"),
        "text": None,
        "rows_to_operations": lambda rows: [],
        "_rows_to_operations": lambda rows: [],
        "to_iso": lambda value: "iso",
        "_to_iso": lambda value: "iso",
        "TIMELINE_PHASE_LOOKBACK": 1,
        "_fetch_latest_heartbeat": lambda *args: None,
        "_summarize_phases": lambda operations: {},
    }
    runtime = create_timeline_runtime(providers)

    assert runtime.build_reservation_timeline("res", 1, 0) == "first"
    providers["HOSTS"] = SimpleNamespace(get_by_lab=lambda value: "second")
    assert runtime.build_reservation_timeline("res", 1, 0) == "second"
