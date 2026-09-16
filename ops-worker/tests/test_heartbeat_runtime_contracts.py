import heartbeat_runtime
from heartbeat_context import HeartbeatContext
from heartbeat_runtime import HeartbeatRuntime, create_heartbeat_runtime


def _context():
    return HeartbeatContext(
        parse_datetime=lambda value: value,
        utc_timezone="UTC",
        now=lambda: "now",
        sql_text=lambda value: value,
        json_dumps=lambda value: "json",
        read_remote_file="read",
        get_db_engine=lambda: "db",
        sync_lab_to_basyx=lambda *args: {},
        resolve_lab_ids_for_host=lambda _host: [],
        get_logger=lambda: "logger",
        get_host_registry=lambda: "hosts",
        get_persist_heartbeat=lambda *args, **kwargs: "persist",
        get_poll_heartbeat=lambda *args, **kwargs: "poll",
        fetch_latest_heartbeat="fetch",
        trust_error_type=RuntimeError,
        missing_credentials_predicate=lambda _error: False,
        trust_error_payload=lambda host, code: {"host": host, "code": code},
        request_id=lambda: "request-id",
        sanitize_log_value=lambda value: str(value),
        credentials_required_message="credentials",
        heartbeat_interval_seconds=10,
        sleep=lambda seconds: None,
    )


def test_heartbeat_runtime_uses_explicit_context_dependencies(monkeypatch):
    calls = []
    monkeypatch.setattr(
        heartbeat_runtime,
        "_to_utc",
        lambda value, **kwargs: calls.append(("utc", value, kwargs)) or "utc",
    )
    monkeypatch.setattr(
        heartbeat_runtime,
        "_persist_heartbeat",
        lambda *args, **kwargs: calls.append(("persist", args, kwargs)),
    )
    monkeypatch.setattr(
        heartbeat_runtime,
        "_poll_heartbeat",
        lambda *args, **kwargs: calls.append(("poll", args, kwargs)) or {"heartbeat": {}},
    )
    monkeypatch.setattr(
        heartbeat_runtime,
        "_generate_heartbeat_stream",
        lambda *args, **kwargs: calls.append(("stream", args, kwargs)) or iter(["event"]),
    )
    monkeypatch.setattr(
        heartbeat_runtime,
        "_poll_all_hosts",
        lambda *args, **kwargs: calls.append(("all", args, kwargs)),
    )
    monkeypatch.setattr(
        heartbeat_runtime,
        "_load_persisted_heartbeat",
        lambda *args, **kwargs: calls.append(("history", args, kwargs)) or {"ready": True},
    )

    context = _context()
    runtime = create_heartbeat_runtime(context)

    assert isinstance(runtime, HeartbeatRuntime)
    assert runtime.to_utc("timestamp") == "utc"
    assert runtime.persist_heartbeat("db", {"name": "host"}, {}, None) is None
    assert runtime.poll_heartbeat({"name": "host"}, include_events=True) == {"heartbeat": {}}
    assert runtime.format_sse_event("heartbeat", "{}") == "event: heartbeat\ndata: {}\n\n"
    assert list(runtime.generate_heartbeat_stream({"name": "host"}, False)) == ["event"]
    assert runtime.poll_all_hosts() is None
    assert runtime.load_persisted_heartbeat("lab-1", {"name": "host"}) == {"ready": True}

    assert calls[0][0] == "utc"
    assert calls[1][0] == "persist"
    assert calls[2][0] == "poll"
    assert calls[2][2]["read_remote_file"] == "read"
    assert calls[2][2]["persist_heartbeat"] is context.get_persist_heartbeat
    assert calls[3][0] == "stream"
    assert calls[4][0] == "all"
    assert calls[5][0] == "history"


def test_heartbeat_context_is_immutable():
    context = _context()

    try:
        context.get_db_engine = lambda: "replacement"
    except AttributeError:
        pass
    else:
        raise AssertionError("HeartbeatContext must be immutable")
