from unittest.mock import Mock

from flask import Flask

import worker
from local_mode_blueprint import create_local_mode_blueprint


def _blueprint(**overrides):
    providers = {
        "parse_bool": lambda value, default: bool(value) if value is not None else default,
        "find_host": lambda _name: {"name": "lab-ws-01"},
        "get_flag_path": lambda _host: r"C:\LabStation\labstation\data\local-mode.flag",
        "write_remote_file": lambda *_args: None,
        "remove_remote_file": lambda *_args: None,
        "internal_error_response": lambda message, exc, **kwargs: (
            {"error": message},
            500,
        ),
    }
    providers.update(overrides)
    return create_local_mode_blueprint(**providers)


def test_local_mode_blueprint_registers_expected_route():
    app = Flask("local-mode-blueprint-contract")
    app.register_blueprint(_blueprint())

    rules = [rule for rule in app.url_map.iter_rules() if rule.rule == "/api/hosts/local-mode"]

    assert len(rules) == 1
    assert rules[0].methods == {"POST", "OPTIONS"}
    assert rules[0].endpoint == "local_mode.api_hosts_local_mode"


def test_local_mode_blueprint_forwards_enable_and_disable_operations():
    app = Flask("local-mode-forwarding-contract")
    host = {"name": "lab-ws-01"}
    calls = []
    app.register_blueprint(
        _blueprint(
            find_host=lambda name: calls.append(("find", name)) or host,
            get_flag_path=lambda value: calls.append(("path", value)) or r"C:\flags\local-mode.flag",
            parse_bool=lambda value, _default: value in {True, "yes"},
            write_remote_file=lambda *args: calls.append(("write", *args)),
            remove_remote_file=lambda *args: calls.append(("remove", *args)),
        )
    )
    client = app.test_client()

    enable = client.post("/api/hosts/local-mode", json={"host": "lab-ws-01", "enabled": "yes"})
    disable = client.post("/api/hosts/local-mode", json={"host": "lab-ws-01", "enabled": False})

    assert enable.status_code == 200
    assert enable.get_json() == {"host": "lab-ws-01", "localModeEnabled": True}
    assert disable.status_code == 200
    assert disable.get_json() == {"host": "lab-ws-01", "localModeEnabled": False}
    assert calls == [
        ("find", "lab-ws-01"),
        ("path", host),
        ("write", host, r"C:\flags\local-mode.flag", "1", None, None, None, None, None),
        ("find", "lab-ws-01"),
        ("path", host),
        ("remove", host, r"C:\flags\local-mode.flag", None, None, None, None, None),
    ]


def test_local_mode_blueprint_preserves_validation_lookup_and_error_contracts():
    app = Flask("local-mode-error-contract")
    remote_write = Mock(side_effect=RuntimeError("winrm password leaked in detail"))
    app.register_blueprint(
        _blueprint(
            find_host=lambda name: None if name == "unknown" else {"name": name},
            write_remote_file=remote_write,
        )
    )
    client = app.test_client()

    missing_host = client.post("/api/hosts/local-mode", json={"enabled": True})
    missing_enabled = client.post("/api/hosts/local-mode", json={"host": "known"})
    unknown = client.post(
        "/api/hosts/local-mode", json={"host": "unknown", "enabled": True}
    )
    failed = client.post(
        "/api/hosts/local-mode",
        json={"host": "known", "enabled": True},
        headers={"X-Request-ID": "local-mode-1"},
    )

    assert missing_host.status_code == 400
    assert missing_host.get_json() == {"error": "host is required"}
    assert missing_enabled.status_code == 400
    assert missing_enabled.get_json() == {"error": "enabled is required"}
    assert unknown.status_code == 404
    assert unknown.get_json() == {"error": "host 'unknown' not found"}
    assert failed.status_code == 500
    assert failed.get_json() == {"error": "Local mode toggle failed for known"}
    assert "winrm password leaked in detail" not in failed.get_data(as_text=True)


def test_worker_local_mode_route_is_owned_by_the_blueprint(monkeypatch):
    host = {"name": "lab-ws-01"}
    calls = []
    monkeypatch.setattr(worker.HOSTS, "get", lambda name: host if name == host["name"] else None)
    monkeypatch.setattr(worker, "parse_bool", lambda value, default: value in {True, "yes"})
    monkeypatch.setattr(
        worker,
        "get_local_mode_flag_path",
        lambda value: calls.append(("path", value)) or r"C:\flags\local-mode.flag",
    )
    monkeypatch.setattr(
        worker,
        "write_remote_file",
        lambda *args: calls.append(("write", *args)),
    )
    monkeypatch.setattr(worker, "remove_remote_file", lambda *args: calls.append(("remove", *args)))

    rules = [rule for rule in worker.APP.url_map.iter_rules() if rule.rule == "/api/hosts/local-mode"]
    assert len(rules) == 1
    assert rules[0].endpoint == "local_mode.api_hosts_local_mode"
    assert callable(worker.api_hosts_local_mode)

    response = worker.APP.test_client().post(
        "/api/hosts/local-mode", json={"host": "lab-ws-01", "enabled": "yes"}
    )

    assert response.status_code == 200
    assert response.json == {"host": "lab-ws-01", "localModeEnabled": True}
    assert calls == [
        ("path", host),
        ("write", host, r"C:\flags\local-mode.flag", "1", None, None, None, None, None),
    ]
