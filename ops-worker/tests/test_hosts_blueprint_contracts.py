from flask import Flask

import worker
from hosts_blueprint import create_hosts_blueprint


def test_hosts_blueprint_registers_the_inventory_route_with_injected_provider():
    app = Flask("hosts-blueprint-contract")
    calls = []
    inventory = {
        "hosts": [{"name": "lab-ws-01"}],
        "guacamoleAvailable": True,
        "guacamoleError": None,
        "guacamoleUnmatched": [],
    }

    app.register_blueprint(
        create_hosts_blueprint(
            build_inventory=lambda: calls.append("inventory") or inventory,
        )
    )

    rules = [rule for rule in app.url_map.iter_rules() if rule.rule == "/api/hosts"]
    assert len(rules) == 1
    assert rules[0].methods == {"GET", "HEAD", "OPTIONS"}
    assert rules[0].endpoint == "hosts.api_hosts_inventory"

    response = app.test_client().get("/api/hosts")

    assert response.status_code == 200
    assert response.get_json() == inventory
    assert calls == ["inventory"]


def test_worker_inventory_route_is_owned_by_the_blueprint_without_duplicates():
    rules = [rule for rule in worker.APP.url_map.iter_rules() if rule.rule == "/api/hosts"]

    assert len(rules) == 1
    assert rules[0].endpoint == "hosts.api_hosts_inventory"
    assert callable(worker.api_hosts_inventory)
