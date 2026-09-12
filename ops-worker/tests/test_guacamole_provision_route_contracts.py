from unittest.mock import Mock

import worker


def test_guacamole_provision_route_contract_short_circuits_authorization(client, monkeypatch):
    unauthorized = {"success": False, "error": "Unauthorized"}, 401
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: unauthorized)

    response = client.post("/internal/guacamole/provision", json={})

    assert response.status_code == 401
    assert response.json == {"success": False, "error": "Unauthorized"}


def test_guacamole_provision_route_contract_forwards_normalized_request(client, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: None)
    monkeypatch.setattr(
        worker,
        "provision_guacamole_temporary_user",
        lambda selector, session_id, valid_until, activate: calls.append(
            (selector, session_id, valid_until, activate)
        ) or {"success": True, "username": "temp-session-1"},
    )

    response = client.post(
        "/internal/guacamole/provision",
        json={
            "selector": "  guac:id:7 ",
            "sessionId": " session-1 ",
            "validUntilEpochSeconds": 1800000000,
            "activate": False,
        },
    )

    assert response.status_code == 200
    assert response.json == {"success": True, "username": "temp-session-1"}
    assert calls == [("guac:id:7", "session-1", 1800000000, False)]


def test_guacamole_provision_route_contract_rejects_non_boolean_activate(client, monkeypatch):
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: None)
    provision = Mock()
    monkeypatch.setattr(worker, "provision_guacamole_temporary_user", provision)

    response = client.post(
        "/internal/guacamole/provision",
        json={"selector": "guac:id:7", "sessionId": "session-1", "activate": "false"},
    )

    assert response.status_code == 400
    assert response.json == {"success": False, "error": "activate must be a boolean"}
    provision.assert_not_called()


def test_guacamole_provision_route_contract_maps_value_errors_to_400(client, monkeypatch):
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: None)
    monkeypatch.setattr(
        worker,
        "provision_guacamole_temporary_user",
        Mock(side_effect=ValueError("invalid selector")),
    )

    response = client.post(
        "/internal/guacamole/provision",
        json={"selector": "bad", "sessionId": "session-1"},
    )

    assert response.status_code == 400
    assert response.json == {"success": False, "error": "Invalid Guacamole provisioning request"}


def test_guacamole_provision_route_contract_hides_unexpected_errors(client, monkeypatch):
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: None)
    monkeypatch.setattr(
        worker,
        "provision_guacamole_temporary_user",
        Mock(side_effect=RuntimeError("secret provisioning details")),
    )

    response = client.post(
        "/internal/guacamole/provision",
        json={"selector": "guac:id:7", "sessionId": "session-1"},
        headers={"X-Request-ID": "guac-provision-1"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "guac-provision-1",
        "success": False,
    }
    assert "secret provisioning details" not in response.get_data(as_text=True)
