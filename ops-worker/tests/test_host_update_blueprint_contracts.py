from flask import Flask

import worker
from host_update_blueprint import create_host_update_blueprint


def _blueprint(**overrides):
    providers = {
        "update_host": lambda _name, _payload: ({"name": "lab-ws-01"}, None),
        "reload_hosts": lambda: (4, None),
        "safe_host_inventory_entry": lambda host, **kwargs: {
            "name": host["name"],
            "editable": kwargs["editable"],
        },
        "internal_error_response": lambda message, exc: ({"error": message}, 500),
    }
    providers.update(overrides)
    return create_host_update_blueprint(**providers)


def test_host_update_blueprint_registers_expected_route():
    app = Flask("host-update-blueprint-contract")
    app.register_blueprint(_blueprint())

    rules = [rule for rule in app.url_map.iter_rules() if rule.rule == "/api/hosts/<host_name>"]

    assert len(rules) == 1
    assert rules[0].methods == {"PATCH", "OPTIONS"}
    assert rules[0].endpoint == "host_update.api_hosts_update"


def test_host_update_blueprint_forwards_payload_and_editable_projection():
    app = Flask("host-update-forwarding-contract")
    host_config = {"name": "lab-ws-01", "address": "192.168.1.50"}
    calls = []
    app.register_blueprint(
        _blueprint(
            update_host=lambda name, payload: calls.append(("update", name, payload))
            or (host_config, None),
            reload_hosts=lambda: calls.append(("reload",)) or (7, None),
            safe_host_inventory_entry=lambda host, **kwargs: calls.append(
                ("safe", host, kwargs)
            )
            or {"name": host["name"], "editable": kwargs["editable"]},
        )
    )

    response = app.test_client().patch(
        "/api/hosts/lab-ws-01",
        json={"mac": "00-11-22-33-44-55"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "updated": True,
        "hosts": 7,
        "host": {"name": "lab-ws-01", "editable": True},
    }
    assert calls == [
        ("update", "lab-ws-01", {"mac": "00-11-22-33-44-55"}),
        ("reload",),
        ("safe", host_config, {"editable": True}),
    ]


def test_host_update_blueprint_preserves_non_object_and_catalog_error_contracts():
    app = Flask("host-update-error-contract")
    app.register_blueprint(
        _blueprint(
            update_host=lambda _name, _payload: (
                None,
                "host is defined in the static catalog; edit manually",
            ),
        )
    )
    client = app.test_client()

    invalid_payload = client.patch("/api/hosts/lab-ws-01", json=[{"name": "invalid"}])
    conflict = client.patch("/api/hosts/lab-ws-01", json={"name": "renamed"})

    assert invalid_payload.status_code == 400
    assert invalid_payload.get_json() == {"error": "host update payload must be an object"}
    assert conflict.status_code == 409
    assert conflict.get_json() == {
        "error": "host is defined in the static catalog; edit manually"
    }


def test_worker_host_update_route_is_owned_by_the_blueprint(monkeypatch):
    host_config = {"name": "lab-ws-01", "address": "192.168.1.50"}
    monkeypatch.setattr(
        worker,
        "update_dynamic_host",
        lambda name, payload: (host_config, None),
    )
    monkeypatch.setattr(worker, "reload_hosts", lambda: (7, None))
    monkeypatch.setattr(
        worker,
        "safe_host_inventory_entry",
        lambda host, **kwargs: {"name": host["name"], "editable": kwargs["editable"]},
    )

    rules = [rule for rule in worker.APP.url_map.iter_rules() if rule.rule == "/api/hosts/<host_name>"]
    assert len(rules) == 1
    assert rules[0].endpoint == "host_update.api_hosts_update"

    response = worker.APP.test_client().patch(
        "/api/hosts/lab-ws-01", json={"mac": "00-11-22-33-44-55"}
    )

    assert response.status_code == 200
    assert response.json == {
        "updated": True,
        "hosts": 7,
        "host": {"name": "lab-ws-01", "editable": True},
    }
