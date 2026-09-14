import worker
from flask import Flask

from hosts_reload_blueprint import create_hosts_reload_blueprint


def test_hosts_reload_blueprint_preserves_count_and_failure_contract():
    app = Flask("hosts-reload-blueprint-contract")
    calls = []

    app.register_blueprint(
        create_hosts_reload_blueprint(
            reload_hosts=lambda: calls.append("reload") or (3, None),
        )
    )

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/hosts/reload"
    ]
    assert len(rules) == 1
    assert rules[0].methods == {"POST", "OPTIONS"}
    assert rules[0].endpoint == "hosts_reload.api_hosts_reload"

    response = app.test_client().post("/api/hosts/reload")

    assert response.status_code == 200
    assert response.get_json() == {"reloaded": True, "hosts": 3}
    assert calls == ["reload"]


def test_hosts_reload_blueprint_maps_reload_errors_without_details():
    app = Flask("hosts-reload-error-blueprint-contract")
    app.register_blueprint(
        create_hosts_reload_blueprint(
            reload_hosts=lambda: (3, "secret catalog details"),
        )
    )

    response = app.test_client().post("/api/hosts/reload")

    assert response.status_code == 500
    assert response.get_json() == {"error": "Hosts configuration reload failed"}
    assert "secret catalog details" not in response.get_data(as_text=True)


def test_worker_hosts_reload_route_is_owned_by_the_blueprint_and_resolves_runtime_provider(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "reload_hosts", lambda: calls.append("reload") or (5, None))

    rules = [
        rule for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/api/hosts/reload"
    ]
    assert len(rules) == 1
    assert rules[0].endpoint == "hosts_reload.api_hosts_reload"

    response = worker.APP.test_client().post("/api/hosts/reload")

    assert response.status_code == 200
    assert response.json == {"reloaded": True, "hosts": 5}
    assert calls == ["reload"]
