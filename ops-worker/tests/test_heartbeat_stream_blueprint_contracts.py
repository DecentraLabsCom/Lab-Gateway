from flask import Flask, Response

import worker
from heartbeat_stream_blueprint import create_heartbeat_stream_blueprint


def test_heartbeat_stream_blueprint_preserves_sse_headers_and_query_contract():
    app = Flask("heartbeat-stream-blueprint-contract")
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    calls = []

    app.register_blueprint(
        create_heartbeat_stream_blueprint(
            find_host=lambda value: host if value == "lab-ws-01" else None,
            generate_stream=lambda value, include_events: calls.append(
                (value, include_events)
            ) or iter(["event: heartbeat\\ndata: {}\\n\\n"]),
            response_factory=Response,
            stream_with_context=lambda iterable: iterable,
        )
    )

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/heartbeat/stream"
    ]
    assert len(rules) == 1
    assert rules[0].methods == {"GET", "HEAD", "OPTIONS"}
    assert rules[0].endpoint == "heartbeat_stream.api_stream_heartbeat"

    response = app.test_client().get(
        "/api/heartbeat/stream?host=lab-ws-01&include_events=off"
    )

    assert response.status_code == 200
    assert response.content_type == "text/event-stream"
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.get_data(as_text=True) == "event: heartbeat\\ndata: {}\\n\\n"
    assert calls == [(host, False)]


def test_worker_heartbeat_stream_route_is_owned_by_the_blueprint_without_duplicates():
    rules = [
        rule for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/api/heartbeat/stream"
    ]

    assert len(rules) == 1
    assert rules[0].endpoint == "heartbeat_stream.api_stream_heartbeat"
    assert callable(worker.api_stream_heartbeat)


def test_worker_heartbeat_stream_blueprint_resolves_runtime_dependencies(monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    calls = []
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(
        worker,
        "generate_heartbeat_stream",
        lambda value, include_events: calls.append((value, include_events))
        or iter(["event: heartbeat\\ndata: {}\\n\\n"]),
    )

    response = worker.APP.test_client().get(
        "/api/heartbeat/stream?host=lab-ws-01&include_events=no"
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "event: heartbeat\\ndata: {}\\n\\n"
    assert calls == [(host, False)]
