from flask import Flask

import worker
from winrm_trust_blueprint import create_winrm_trust_blueprint


def test_winrm_trust_blueprint_preserves_projection_and_request_id_contract():
    app = Flask("winrm-trust-blueprint-contract")
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    trust = {"configured": True, "status": "ready"}

    app.register_blueprint(
        create_winrm_trust_blueprint(
            find_host=lambda value: host if value == "lab-ws-01" else None,
            inspect_trust=lambda value: trust if value is host else {},
            request_id=lambda: "trust-blueprint-1",
            trust_error_type=RuntimeError,
            trust_error_payload=lambda host_name, code: {
                "host": host_name,
                "code": code,
            },
            trust_http_status=lambda _code: 422,
            internal_error_response=lambda _message, _exc: ({"error": "internal"}, 500),
        )
    )

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/hosts/<host_name>/winrm-trust"
    ]
    assert len(rules) == 1
    assert rules[0].methods == {"GET", "HEAD", "OPTIONS"}
    assert rules[0].endpoint == "winrm_trust.api_get_winrm_trust"

    response = app.test_client().get("/api/hosts/lab-ws-01/winrm-trust")

    assert response.status_code == 200
    assert response.get_json() == {
        "requestId": "trust-blueprint-1",
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "trust": trust,
    }


def test_worker_winrm_trust_get_route_is_owned_by_the_blueprint_without_duplicates():
    rules = [
        rule for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/api/hosts/<host_name>/winrm-trust"
        and "GET" in rule.methods
    ]

    assert len(rules) == 1
    assert rules[0].endpoint == "winrm_trust.api_get_winrm_trust"
    assert callable(worker.api_get_winrm_trust)


def test_worker_winrm_trust_get_blueprint_resolves_runtime_dependencies(monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    trust = {"configured": True, "status": "ready"}
    inspected = []
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(worker, "inspect_winrm_trust", lambda value: inspected.append(value) or trust)
    monkeypatch.setattr(worker, "_request_id", lambda: "trust-blueprint-2")

    response = worker.APP.test_client().get("/api/hosts/lab-ws-01/winrm-trust")

    assert response.status_code == 200
    assert response.json["requestId"] == "trust-blueprint-2"
    assert response.json["trust"] == trust
    assert inspected == [host]
