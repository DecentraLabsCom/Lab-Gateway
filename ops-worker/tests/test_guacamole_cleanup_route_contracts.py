from unittest.mock import Mock

import worker


def test_guacamole_cleanup_route_contract_short_circuits_authorization(client, monkeypatch):
    unauthorized = {"success": False, "error": "Unauthorized"}, 401
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: unauthorized)

    response = client.delete("/internal/guacamole/provision/session-1")

    assert response.status_code == 401
    assert response.json == {"success": False, "error": "Unauthorized"}


def test_guacamole_cleanup_route_contract_returns_deleted_state(client, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: None)
    monkeypatch.setattr(
        worker,
        "delete_guacamole_temporary_user",
        lambda session_id: calls.append(session_id) or True,
    )

    response = client.delete("/internal/guacamole/provision/session-1")

    assert response.status_code == 200
    assert response.json == {
        "success": True,
        "deleted": True,
        "sessionId": "session-1",
    }
    assert calls == ["session-1"]


def test_guacamole_cleanup_route_contract_maps_invalid_session_to_400(client, monkeypatch):
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: None)
    monkeypatch.setattr(
        worker,
        "delete_guacamole_temporary_user",
        Mock(side_effect=ValueError("invalid session")),
    )

    response = client.delete("/internal/guacamole/provision/session-1")

    assert response.status_code == 400
    assert response.json == {
        "success": False,
        "error": "Invalid Guacamole cleanup request",
    }


def test_guacamole_cleanup_route_contract_hides_unexpected_errors(client, monkeypatch):
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: None)
    monkeypatch.setattr(
        worker,
        "delete_guacamole_temporary_user",
        Mock(side_effect=RuntimeError("secret cleanup details")),
    )

    response = client.delete(
        "/internal/guacamole/provision/session-1",
        headers={"X-Request-ID": "guac-cleanup-1"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "guac-cleanup-1",
        "success": False,
    }
    assert "secret cleanup details" not in response.get_data(as_text=True)
