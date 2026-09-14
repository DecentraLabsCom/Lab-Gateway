from flask import Flask

import worker
from host_provision_blueprint import create_host_provision_blueprint


def _blueprint(**overrides):
    providers = {
        "resolve_connection": lambda _value: {"id": 42, "name": "Provisionable"},
        "discover_candidate": lambda _connection: {"status": "labstation-detected"},
        "enough_discovery_signals": {"labstation-detected"},
        "build_host": lambda _payload, _connection: (
            {"name": "lab-ws-42", "address": "192.168.1.50"},
            None,
        ),
        "find_host": lambda _name: None,
        "upsert_host": lambda _host: None,
        "reload_hosts": lambda: (5, None),
        "safe_host_inventory_entry": lambda host, **kwargs: {
            "name": host["name"],
            "editable": kwargs["editable"],
        },
        "internal_error_response": lambda message, exc: ({"error": message}, 500),
    }
    providers.update(overrides)
    return create_host_provision_blueprint(**providers)


def test_host_provision_blueprint_registers_expected_route():
    app = Flask("host-provision-blueprint-contract")
    app.register_blueprint(_blueprint())

    rules = [rule for rule in app.url_map.iter_rules() if rule.rule == "/api/hosts/provision"]

    assert len(rules) == 1
    assert rules[0].methods == {"POST", "OPTIONS"}
    assert rules[0].endpoint == "host_provision.api_hosts_provision"


def test_host_provision_blueprint_forwards_alias_and_discovery_contract():
    app = Flask("host-provision-forwarding-contract")
    connection = {"id": 42, "name": "Provisionable"}
    host_config = {"name": "lab-ws-42", "address": "192.168.1.50"}
    calls = []
    app.register_blueprint(
        _blueprint(
            resolve_connection=lambda value: calls.append(("resolve", value)) or connection,
            discover_candidate=lambda value: calls.append(("discover", value))
            or {"status": "labstation-detected"},
            build_host=lambda payload, value: calls.append(("build", payload, value))
            or (host_config, None),
            find_host=lambda value: calls.append(("find", value)) or None,
            upsert_host=lambda value: calls.append(("upsert", value)),
            reload_hosts=lambda: calls.append(("reload",)) or (5, None),
            safe_host_inventory_entry=lambda host, **kwargs: calls.append(
                ("safe", host, kwargs)
            )
            or {"name": host["name"], "editable": kwargs["editable"]},
        )
    )

    response = app.test_client().post(
        "/api/hosts/provision",
        json={"connection_id": 42, "name": "lab-ws-42"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "provisioned": True,
        "hosts": 5,
        "host": {"name": "lab-ws-42", "editable": True},
        "discoveryStatus": "labstation-detected",
    }
    assert calls == [
        ("resolve", 42),
        ("discover", connection),
        ("build", {"connection_id": 42, "name": "lab-ws-42"}, connection),
        ("find", "lab-ws-42"),
        ("upsert", host_config),
        ("reload",),
        ("safe", host_config, {"editable": True}),
    ]


def test_host_provision_blueprint_preserves_discovery_and_conflict_errors():
    app = Flask("host-provision-errors-contract")
    app.register_blueprint(
        _blueprint(
            discover_candidate=lambda _connection: {
                "status": "host-resolves",
                "checks": {"winrm": False},
            },
        )
    )
    insufficient = app.test_client().post("/api/hosts/provision", json={"connectionId": 42})

    app = Flask("host-provision-conflict-contract")
    app.register_blueprint(
        _blueprint(
            find_host=lambda _name: {"name": "lab-ws-42"},
        )
    )
    conflict = app.test_client().post("/api/hosts/provision", json={"connectionId": 42})

    assert insufficient.status_code == 409
    assert insufficient.get_json() == {
        "error": "insufficient discovery signal for ops host provisioning",
        "discovery": {"status": "host-resolves", "checks": {"winrm": False}},
    }
    assert conflict.status_code == 409
    assert conflict.get_json() == {"error": "host lab-ws-42 already exists"}


def test_worker_host_provision_route_is_owned_by_the_blueprint(monkeypatch):
    connection = {"id": 42, "name": "Provisionable"}
    host_config = {"name": "lab-ws-42", "address": "192.168.1.50"}
    monkeypatch.setattr(worker, "resolve_guacamole_connection", lambda _value: connection)
    monkeypatch.setattr(worker, "discover_labstation_candidate", lambda _value: {"status": "labstation-detected"})
    monkeypatch.setattr(worker, "build_provisioned_host", lambda _payload, _connection: (host_config, None))
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": []}))
    monkeypatch.setattr(worker, "upsert_dynamic_host", lambda _host: None)
    monkeypatch.setattr(worker, "reload_hosts", lambda: (5, None))
    monkeypatch.setattr(
        worker,
        "safe_host_inventory_entry",
        lambda host, **kwargs: {"name": host["name"], "editable": kwargs["editable"]},
    )

    rules = [rule for rule in worker.APP.url_map.iter_rules() if rule.rule == "/api/hosts/provision"]
    assert len(rules) == 1
    assert rules[0].endpoint == "host_provision.api_hosts_provision"

    response = worker.APP.test_client().post(
        "/api/hosts/provision", json={"connectionId": 42}
    )

    assert response.status_code == 200
    assert response.json == {
        "provisioned": True,
        "hosts": 5,
        "host": {"name": "lab-ws-42", "editable": True},
        "discoveryStatus": "labstation-detected",
    }
