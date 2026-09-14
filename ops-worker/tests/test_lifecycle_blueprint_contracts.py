import pytest
from flask import Flask

import worker
from lifecycle_blueprint import create_lifecycle_blueprint


PATHS = (
    ("/api/reservations/start", "api_reservation_start"),
    ("/api/reservations/end", "api_reservation_end"),
    ("/api/demo/start", "api_demo_start"),
    ("/api/demo/event", "api_demo_event"),
    ("/api/demo/end", "api_demo_end"),
)


def _blueprint(**overrides):
    providers = {
        "reservation_start": lambda payload: ({"operation": "reservation-start", "payload": payload}, 200),
        "reservation_end": lambda payload: ({"operation": "reservation-end", "payload": payload}, 200),
        "demo_start": lambda payload: ({"operation": "demo-start", "payload": payload}, 200),
        "demo_event": lambda payload: ({"operation": "demo-event", "payload": payload}, 200),
        "demo_end": lambda payload: ({"operation": "demo-end", "payload": payload}, 200),
    }
    providers.update(overrides)
    return create_lifecycle_blueprint(**providers)


def test_lifecycle_blueprint_registers_all_five_routes():
    app = Flask("lifecycle-blueprint-contract")
    app.register_blueprint(_blueprint())

    rules = {
        rule.rule: rule
        for rule in app.url_map.iter_rules()
        if rule.rule in {path for path, _handler in PATHS}
    }

    assert set(rules) == {path for path, _handler in PATHS}
    for path, handler in PATHS:
        assert rules[path].methods == {"POST", "OPTIONS"}
        assert rules[path].endpoint == f"lifecycle.{handler}"


@pytest.mark.parametrize(
    ("path", "provider"),
    [
        ("/api/reservations/start", "reservation_start"),
        ("/api/reservations/end", "reservation_end"),
        ("/api/demo/start", "demo_start"),
        ("/api/demo/event", "demo_event"),
        ("/api/demo/end", "demo_end"),
    ],
)
def test_lifecycle_blueprint_forwards_payload_result_and_status(path, provider):
    app = Flask("lifecycle-forwarding-contract")
    calls = []
    app.register_blueprint(
        _blueprint(
            **{
                provider: lambda payload: calls.append(payload)
                or ({"success": True, "provider": provider}, 201)
            }
        )
    )

    payload = {"reservationId": "r-1", "event": "connected"}
    response = app.test_client().post(path, json=payload)

    assert response.status_code == 201
    assert response.get_json() == {"success": True, "provider": provider}
    assert calls == [payload]


def test_worker_lifecycle_routes_are_owned_by_the_blueprint_and_resolve_handlers_dynamically(
    monkeypatch,
):
    calls = []
    handlers = {
        "handle_reservation_start": {"path": "/api/reservations/start", "result": {"route": "reservation-start"}},
        "handle_reservation_end": {"path": "/api/reservations/end", "result": {"route": "reservation-end"}},
        "handle_demo_start": {"path": "/api/demo/start", "result": {"route": "demo-start"}},
        "handle_demo_event": {"path": "/api/demo/event", "result": {"route": "demo-event"}},
        "handle_demo_end": {"path": "/api/demo/end", "result": {"route": "demo-end"}},
    }
    for name, config in handlers.items():
        monkeypatch.setattr(
            worker,
            name,
            lambda payload, *, _name=name, _result=config["result"]: calls.append((_name, payload))
            or (_result, 200),
        )

    rules = [
        rule
        for rule in worker.APP.url_map.iter_rules()
        if rule.rule in {config["path"] for config in handlers.values()}
    ]
    assert len(rules) == 5
    assert {rule.endpoint for rule in rules} == {
        "lifecycle.api_reservation_start",
        "lifecycle.api_reservation_end",
        "lifecycle.api_demo_start",
        "lifecycle.api_demo_event",
        "lifecycle.api_demo_end",
    }

    client = worker.APP.test_client()
    for name, config in handlers.items():
        response = client.post(config["path"], json={"source": name})
        assert response.status_code == 200
        assert response.json == config["result"]

    assert calls == [(name, {"source": name}) for name in handlers]
