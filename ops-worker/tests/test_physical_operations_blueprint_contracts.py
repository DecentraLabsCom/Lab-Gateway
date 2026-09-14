from flask import Flask

import worker
from physical_operations_blueprint import create_physical_operations_blueprint


def _blueprint(**overrides):
    providers = {
        "find_host": lambda _value: {
            "name": "lab-ws-01",
            "address": "192.168.1.50",
            "mac": "00:11:22:33:44:55",
        },
        "is_valid_ping_target": lambda _value: True,
        "wol_and_wait": lambda *_args, **_kwargs: (True, 1),
        "now": lambda: 100.0,
        "allowed_commands": {"status-json"},
        "run_command": lambda **_kwargs: {"exit_code": 0, "stdout": "ok", "stderr": ""},
        "trust_error_type": worker.WinRMTrustError,
        "trust_error_payload": lambda host_name, code: {"host": host_name, "code": code},
        "internal_error_response": lambda message, exc: ({"error": message}, 500),
    }
    providers.update(overrides)
    return create_physical_operations_blueprint(**providers)


def test_physical_operations_blueprint_registers_wol_and_winrm_routes():
    app = Flask("physical-operations-blueprint-contract")
    app.register_blueprint(_blueprint())

    rules = {
        rule.rule: rule
        for rule in app.url_map.iter_rules()
        if rule.rule in {"/api/wol", "/api/winrm"}
    }

    assert set(rules) == {"/api/wol", "/api/winrm"}
    assert rules["/api/wol"].methods == {"POST", "OPTIONS"}
    assert rules["/api/wol"].endpoint == "physical_operations.api_wol"
    assert rules["/api/winrm"].methods == {"POST", "OPTIONS"}
    assert rules["/api/winrm"].endpoint == "physical_operations.api_winrm"


def test_physical_operations_blueprint_forwards_wol_contract():
    app = Flask("physical-operations-wol-contract")
    calls = []
    app.register_blueprint(
        _blueprint(
            wol_and_wait=lambda *args, **kwargs: calls.append((args, kwargs)) or (True, 2),
        )
    )

    response = app.test_client().post(
        "/api/wol",
        json={"host": "lab-ws-01", "attempts": 4, "ping_timeout": 1.5},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "attempts_used": 2,
        "duration_ms": 0,
        "ping_target": "192.168.1.50",
    }
    assert calls == [
        (
            ("00:11:22:33:44:55", None, 9, "192.168.1.50", 4, 1.5),
            {"probe_port": None},
        )
    ]


def test_physical_operations_blueprint_forwards_winrm_contract():
    app = Flask("physical-operations-winrm-contract")
    calls = []
    app.register_blueprint(
        _blueprint(
            run_command=lambda **kwargs: calls.append(kwargs)
            or {"exit_code": 0, "stdout": "ok", "stderr": ""},
        )
    )

    response = app.test_client().post(
        "/api/winrm",
        json={
            "host": "lab-ws-01",
            "command": "status-json",
            "args": ["--compact"],
            "transport": "ntlm",
            "use_ssl": True,
            "port": 5986,
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"exit_code": 0, "stdout": "ok", "stderr": ""}
    assert calls == [
        {
            "host": {
                "name": "lab-ws-01",
                "address": "192.168.1.50",
                "mac": "00:11:22:33:44:55",
            },
            "command": "status-json",
            "args": ["--compact"],
            "user": None,
            "password": None,
            "transport": "ntlm",
            "use_ssl": True,
            "port": 5986,
        }
    ]


def test_worker_physical_operations_routes_are_owned_by_the_blueprint(monkeypatch):
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "mac": "00:11:22:33:44:55",
    }
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(worker, "wol_and_wait", lambda *args, **kwargs: (True, 1))
    monkeypatch.setattr(
        worker,
        "run_labstation_command",
        lambda **kwargs: {"exit_code": 0, "stdout": "ok", "stderr": ""},
    )

    rules = [
        rule for rule in worker.APP.url_map.iter_rules() if rule.rule in {"/api/wol", "/api/winrm"}
    ]
    assert len(rules) == 2
    assert {rule.endpoint for rule in rules} == {
        "physical_operations.api_wol",
        "physical_operations.api_winrm",
    }

    client = worker.APP.test_client()
    wol_response = client.post("/api/wol", json={"host": "lab-ws-01"})
    winrm_response = client.post(
        "/api/winrm", json={"host": "lab-ws-01", "command": "status-json"}
    )

    assert wol_response.status_code == 200
    assert winrm_response.status_code == 200
