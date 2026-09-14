from flask import Flask

import worker
from hosts_discover_blueprint import create_hosts_discover_blueprint


def test_hosts_discover_blueprint_preserves_alias_and_projection_contract():
    app = Flask("hosts-discover-blueprint-contract")
    connection = {"id": 7, "name": "RDP Lab", "hostname": "lab-ws-07"}
    discovery = {"status": "labstation-detected", "connection": connection}
    calls = []

    app.register_blueprint(
        create_hosts_discover_blueprint(
            resolve_connection=lambda value: calls.append(("resolve", value)) or connection,
            discover_candidate=lambda value: calls.append(("discover", value)) or discovery,
        )
    )

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/hosts/discover"
    ]
    assert len(rules) == 1
    assert rules[0].methods == {"POST", "OPTIONS"}
    assert rules[0].endpoint == "hosts_discover.api_hosts_discover"

    response = app.test_client().post(
        "/api/hosts/discover",
        json={"connection_id": 7},
    )

    assert response.status_code == 200
    assert response.get_json() == discovery
    assert calls == [("resolve", 7), ("discover", connection)]


def test_hosts_discover_blueprint_preserves_missing_connection_error():
    app = Flask("hosts-discover-error-blueprint-contract")
    app.register_blueprint(
        create_hosts_discover_blueprint(
            resolve_connection=lambda _value: None,
            discover_candidate=lambda _value: {},
        )
    )

    response = app.test_client().post(
        "/api/hosts/discover",
        json={"connectionId": 999},
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Guacamole connection 999 not found"}


def test_worker_hosts_discover_route_is_owned_by_the_blueprint_and_resolves_runtime_providers(monkeypatch):
    connection = {"id": 7, "name": "RDP Lab", "hostname": "lab-ws-07"}
    discovery = {"status": "labstation-detected", "connection": connection}
    calls = []
    monkeypatch.setattr(
        worker,
        "resolve_guacamole_connection",
        lambda value: calls.append(("resolve", value)) or connection,
    )
    monkeypatch.setattr(
        worker,
        "discover_labstation_candidate",
        lambda value: calls.append(("discover", value)) or discovery,
    )

    rules = [
        rule for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/api/hosts/discover"
    ]
    assert len(rules) == 1
    assert rules[0].endpoint == "hosts_discover.api_hosts_discover"
    assert callable(worker.api_hosts_discover)

    response = worker.APP.test_client().post(
        "/api/hosts/discover",
        json={"connectionId": 7},
    )

    assert response.status_code == 200
    assert response.json == discovery
    assert calls == [("resolve", 7), ("discover", connection)]
