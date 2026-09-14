from flask import Flask

import worker
from guacamole_provision_blueprint import create_guacamole_provision_blueprint


def _blueprint(**overrides):
    providers = {
        "authorize": lambda: None,
        "provision_temporary_user": lambda selector, session_id, valid_until, activate: {
            "success": True,
            "selector": selector,
            "sessionId": session_id,
            "validUntilEpochSeconds": valid_until,
            "activate": activate,
        },
        "delete_temporary_user": lambda session_id: True,
        "internal_error_response": lambda message, exc, **kwargs: (
            {"error": message, "success": False},
            500,
        ),
    }
    providers.update(overrides)
    return create_guacamole_provision_blueprint(**providers)


def test_guacamole_provision_blueprint_registers_both_resource_methods():
    app = Flask("guacamole-provision-blueprint-contract")
    app.register_blueprint(_blueprint())

    rules = {
        rule.rule: rule
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/internal/guacamole/provision")
    }

    assert set(rules) == {
        "/internal/guacamole/provision",
        "/internal/guacamole/provision/<session_id>",
    }
    assert rules["/internal/guacamole/provision"].methods == {"POST", "OPTIONS"}
    assert rules["/internal/guacamole/provision"].endpoint == (
        "guacamole_provision.api_internal_guacamole_provision"
    )
    assert rules["/internal/guacamole/provision/<session_id>"].methods == {
        "DELETE",
        "OPTIONS",
    }
    assert rules["/internal/guacamole/provision/<session_id>"].endpoint == (
        "guacamole_provision.api_internal_guacamole_delete"
    )


def test_guacamole_provision_blueprint_forwards_post_contract():
    app = Flask("guacamole-provision-post-contract")
    calls = []
    app.register_blueprint(
        _blueprint(
            provision_temporary_user=lambda selector, session_id, valid_until, activate: calls.append(
                (selector, session_id, valid_until, activate)
            )
            or {"success": True, "username": "temp-session-1"}
        )
    )

    response = app.test_client().post(
        "/internal/guacamole/provision",
        json={
            "selector": "  guac:id:7 ",
            "sessionId": " session-1 ",
            "validUntilEpochSeconds": 1800000000,
            "activate": False,
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "username": "temp-session-1"}
    assert calls == [("guac:id:7", "session-1", 1800000000, False)]


def test_guacamole_provision_blueprint_forwards_delete_contract():
    app = Flask("guacamole-provision-delete-contract")
    calls = []
    app.register_blueprint(
        _blueprint(
            delete_temporary_user=lambda session_id: calls.append(session_id) or True,
        )
    )

    response = app.test_client().delete("/internal/guacamole/provision/session-1")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "deleted": True,
        "sessionId": "session-1",
    }
    assert calls == ["session-1"]


def test_guacamole_provision_blueprint_preserves_authorization_short_circuit():
    unauthorized = {"success": False, "error": "Unauthorized"}, 401
    app = Flask("guacamole-provision-auth-contract")
    calls = []
    app.register_blueprint(
        _blueprint(
            authorize=lambda: unauthorized,
            provision_temporary_user=lambda *args: calls.append(args),
            delete_temporary_user=lambda *args: calls.append(args),
        )
    )

    post_response = app.test_client().post("/internal/guacamole/provision", json={})
    delete_response = app.test_client().delete("/internal/guacamole/provision/session-1")

    assert post_response.status_code == 401
    assert post_response.get_json() == {"success": False, "error": "Unauthorized"}
    assert delete_response.status_code == 401
    assert delete_response.get_json() == {"success": False, "error": "Unauthorized"}
    assert calls == []


def test_worker_guacamole_provision_routes_are_owned_by_the_blueprint(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: None)
    monkeypatch.setattr(
        worker,
        "provision_guacamole_temporary_user",
        lambda selector, session_id, valid_until, activate: calls.append(
            ("provision", selector, session_id, valid_until, activate)
        )
        or {"success": True, "username": "temp-session-1"},
    )
    monkeypatch.setattr(
        worker,
        "delete_guacamole_temporary_user",
        lambda session_id: calls.append(("delete", session_id)) or True,
    )

    rules = [
        rule
        for rule in worker.APP.url_map.iter_rules()
        if rule.rule.startswith("/internal/guacamole/provision")
    ]
    assert len(rules) == 2
    assert {rule.endpoint for rule in rules} == {
        "guacamole_provision.api_internal_guacamole_provision",
        "guacamole_provision.api_internal_guacamole_delete",
    }

    client = worker.APP.test_client()
    post_response = client.post(
        "/internal/guacamole/provision",
        json={"selector": "guac:id:7", "sessionId": "session-1"},
    )
    delete_response = client.delete("/internal/guacamole/provision/session-1")

    assert post_response.status_code == 200
    assert delete_response.status_code == 200
    assert calls == [
        ("provision", "guac:id:7", "session-1", None, True),
        ("delete", "session-1"),
    ]
