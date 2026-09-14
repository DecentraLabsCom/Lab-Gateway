from flask import Flask

import worker
from winrm_credentials_blueprint import create_winrm_credentials_blueprint


def _blueprint(**overrides):
    providers = {
        "save_credentials": lambda _ref, _user, _password: None,
        "reload_hosts": lambda: (3, None),
        "normalize_credential_ref": lambda value: str(value or "").strip().lower(),
        "internal_error_response": lambda message, exc: (
            {"error": message},
            500,
        ),
    }
    providers.update(overrides)
    return create_winrm_credentials_blueprint(**providers)


def test_winrm_credentials_blueprint_registers_expected_route():
    app = Flask("winrm-credentials-blueprint-contract")
    app.register_blueprint(_blueprint())

    rules = [
        rule for rule in app.url_map.iter_rules() if rule.rule == "/api/hosts/winrm-credentials"
    ]

    assert len(rules) == 1
    assert rules[0].methods == {"POST", "OPTIONS"}
    assert rules[0].endpoint == "winrm_credentials.api_save_winrm_credentials"


def test_winrm_credentials_blueprint_forwards_aliases_and_hides_password():
    app = Flask("winrm-credentials-forwarding-contract")
    calls = []
    app.register_blueprint(
        _blueprint(
            save_credentials=lambda ref, user, password: calls.append((ref, user, password)),
            reload_hosts=lambda: (4, None),
        )
    )

    response = app.test_client().post(
        "/api/hosts/winrm-credentials",
        json={
            "credential_ref": "  LAB-WS-01 ",
            "username": " .\\LabGatewaySvc ",
            "password": "secret-password",
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "saved": True,
        "credentialRef": "lab-ws-01",
        "hosts": 4,
    }
    assert calls == [("  LAB-WS-01 ", " .\\LabGatewaySvc ", "secret-password")]
    assert "secret-password" not in response.get_data(as_text=True)


def test_winrm_credentials_blueprint_preserves_validation_and_reload_errors():
    app = Flask("winrm-credentials-errors-contract")
    app.register_blueprint(
        _blueprint(
            save_credentials=lambda *_args: (_ for _ in ()).throw(ValueError("invalid")),
        )
    )
    invalid = app.test_client().post(
        "/api/hosts/winrm-credentials",
        json={"credentialRef": "lab-ws-01", "user": "svc", "password": ""},
    )

    app = Flask("winrm-credentials-reload-error-contract")
    app.register_blueprint(
        _blueprint(
            reload_hosts=lambda: (4, "invalid hosts catalog"),
        )
    )
    reload_error = app.test_client().post(
        "/api/hosts/winrm-credentials",
        json={"credentialRef": "lab-ws-01", "user": "svc", "password": "secret-password"},
    )

    assert invalid.status_code == 400
    assert invalid.get_json() == {"error": "Invalid WinRM credentials request"}
    assert reload_error.status_code == 500
    assert reload_error.get_json() == {"error": "Hosts configuration reload failed"}
    assert "secret-password" not in reload_error.get_data(as_text=True)


def test_worker_winrm_credentials_route_is_owned_by_the_blueprint(monkeypatch):
    calls = []
    monkeypatch.setattr(
        worker,
        "save_winrm_credentials",
        lambda ref, user, password: calls.append(("save", ref, user, password)),
    )
    monkeypatch.setattr(worker, "reload_hosts", lambda: (4, None))
    monkeypatch.setattr(worker, "normalize_credential_ref", lambda value: str(value).strip().lower())

    rules = [
        rule for rule in worker.APP.url_map.iter_rules() if rule.rule == "/api/hosts/winrm-credentials"
    ]
    assert len(rules) == 1
    assert rules[0].endpoint == "winrm_credentials.api_save_winrm_credentials"
    assert callable(worker.api_save_winrm_credentials)

    response = worker.APP.test_client().post(
        "/api/hosts/winrm-credentials",
        json={"credentialRef": "LAB-WS-01", "user": "svc", "password": "secret-password"},
    )

    assert response.status_code == 200
    assert response.json == {
        "saved": True,
        "credentialRef": "lab-ws-01",
        "hosts": 4,
    }
    assert calls == [("save", "LAB-WS-01", "svc", "secret-password")]
    assert "secret-password" not in response.get_data(as_text=True)
