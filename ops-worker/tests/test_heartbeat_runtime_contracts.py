from types import SimpleNamespace

from heartbeat_runtime import HeartbeatRuntime, create_heartbeat_runtime


def test_heartbeat_runtime_forwards_poll_persistence_and_sse_dependencies():
    calls = []
    providers = {
        "_to_utc_impl": lambda value, **kwargs: calls.append(("utc", value, kwargs)) or "utc",
        "datetime": SimpleNamespace(fromisoformat="fromisoformat"),
        "timezone": SimpleNamespace(utc="UTC"),
        "_persist_heartbeat_impl": lambda *args, **kwargs: calls.append(("persist", args, kwargs)),
        "to_utc": lambda value: "utc",
        "text": "sql",
        "json": SimpleNamespace(dumps="dumps"),
        "DB_ENGINE": "db",
        "_poll_heartbeat_impl": lambda *args, **kwargs: calls.append(("poll", args, kwargs)) or {"heartbeat": {}},
        "read_remote_file": "read",
        "persist_heartbeat": "persist",
        "aas_generator": SimpleNamespace(sync_lab_to_basyx="sync"),
        "logging": "logger",
        "_format_sse_event_impl": lambda event, data: f"{event}:{data}",
        "_format_sse_event": lambda event, data: f"{event}:{data}",
        "_generate_heartbeat_stream_impl": lambda *args, **kwargs: calls.append(("stream", args, kwargs)) or iter(["event"]),
        "poll_heartbeat": "poll",
        "_winrm_trust_error_payload": "trust-payload",
        "WinRMTrustError": RuntimeError,
        "is_missing_winrm_credentials_error": "missing",
        "_request_id": "request-id",
        "_sanitize_log_value": "sanitize",
        "WINRM_CREDENTIALS_REQUIRED_MESSAGE": "credentials",
        "HEARTBEAT_SSE_INTERVAL_SECONDS": 10,
        "time": SimpleNamespace(sleep="sleep"),
    }
    runtime = create_heartbeat_runtime(providers)

    assert isinstance(runtime, HeartbeatRuntime)
    assert runtime.to_utc("timestamp") == "utc"
    assert runtime.persist_heartbeat("db", {"name": "host"}, {}, None) is None
    assert runtime.poll_heartbeat({"name": "host"}, include_events=True) == {"heartbeat": {}}
    assert runtime.format_sse_event("heartbeat", "{}") == "heartbeat:{}"
    assert list(runtime.generate_heartbeat_stream({"name": "host"}, False)) == ["event"]
    assert any(call[0] == "poll" for call in calls)


def test_heartbeat_runtime_resolves_mutable_polling_callbacks():
    providers = {
        "_poll_all_hosts_impl": lambda hosts, poll, logger: poll(hosts),
        "HOSTS": "hosts",
        "poll_heartbeat": lambda hosts: ("first", hosts),
        "logging": "logger",
    }
    runtime = create_heartbeat_runtime(providers)

    assert runtime.poll_all_hosts() == ("first", "hosts")
    providers["poll_heartbeat"] = lambda hosts: ("second", hosts)
    assert runtime.poll_all_hosts() == ("second", "hosts")


def test_heartbeat_runtime_forwards_persisted_heartbeat_lookup():
    calls = []
    providers = {
        "_load_persisted_heartbeat_impl": lambda *args, **kwargs: calls.append(
            (args, kwargs)
        ) or {"ready": True},
        "DB_ENGINE": "db",
        "_fetch_latest_heartbeat": "fetch",
    }
    runtime = create_heartbeat_runtime(providers)

    assert runtime.load_persisted_heartbeat("lab-1", {"name": "host"}) == {"ready": True}
    assert calls == [
        (
            ("db", "lab-1", {"name": "host"}),
            {"fetch_latest_heartbeat": "fetch"},
        )
    ]
