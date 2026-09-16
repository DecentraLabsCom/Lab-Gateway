from flask import Flask

import worker
from heartbeat_poll_blueprint import create_heartbeat_poll_blueprint


def test_heartbeat_poll_blueprint_preserves_payload_and_error_provider_contract():
    app = Flask("heartbeat-poll-blueprint-contract")
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    calls = []

    app.register_blueprint(
        create_heartbeat_poll_blueprint(
            find_host=lambda value: host if value == "lab-ws-01" else None,
            poll_heartbeat=lambda value, include_events: calls.append(
                (value, include_events)
            ) or {"heartbeat": {"summary": {"ready": True}}},
            now=lambda: 100.125,
            trust_error_type=RuntimeError,
            trust_error_payload=lambda host_name, code: {
                "host": host_name,
                "code": code,
            },
            missing_credentials_predicate=lambda _error: False,
            credentials_required_message=lambda: "credentials required",
            internal_error_response=lambda _message, _exc: ({"error": "internal"}, 500),
        )
    )

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/heartbeat/poll"
    ]
    assert len(rules) == 1
    assert rules[0].methods == {"POST", "OPTIONS"}
    assert rules[0].endpoint == "heartbeat_poll.api_poll_heartbeat"

    response = app.test_client().post(
        "/api/heartbeat/poll",
        json={"host": "lab-ws-01", "include_events": False},
    )

    assert response.status_code == 200
    assert response.get_json()["host"] == "lab-ws-01"
    assert response.get_json()["heartbeat"]["summary"]["ready"] is True
    assert response.get_json()["duration_ms"] == 0
    assert calls == [(host, False)]


def test_worker_heartbeat_poll_route_is_owned_by_the_blueprint_without_duplicates():
    rules = [
        rule for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/api/heartbeat/poll"
    ]

    assert len(rules) == 1
    assert rules[0].endpoint == "heartbeat_poll.api_poll_heartbeat"


def test_worker_heartbeat_poll_blueprint_resolves_runtime_dependencies(monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    inspected = []
    times = iter((10.0, 10.125))
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(
        worker,
        "poll_heartbeat",
        lambda value, include_events: inspected.append((value, include_events))
        or {"heartbeat": {"summary": {"ready": True}}},
    )
    monkeypatch.setattr(worker.time, "time", lambda: next(times))

    response = worker.APP.test_client().post(
        "/api/heartbeat/poll",
        json={"host": "lab-ws-01", "include_events": True},
    )

    assert response.status_code == 200
    payload = response.json
    assert payload is not None
    assert payload["duration_ms"] == 125
    assert inspected == [(host, True)]
