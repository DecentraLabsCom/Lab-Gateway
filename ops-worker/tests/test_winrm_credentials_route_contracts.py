from unittest.mock import Mock

import worker


def test_winrm_credentials_route_contract_forwards_aliases_and_never_returns_password(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        worker,
        "save_winrm_credentials",
        lambda credential_ref, user, password: calls.append((credential_ref, user, password)),
    )
    monkeypatch.setattr(worker, "reload_hosts", lambda: (4, None))
    monkeypatch.setattr(worker, "normalize_credential_ref", lambda value: str(value).strip().lower())

    response = client.post(
        "/api/hosts/winrm-credentials",
        json={
            "credential_ref": "  LAB-WS-01 ",
            "username": " .\\LabGatewaySvc ",
            "password": "secret-password",
        },
    )

    assert response.status_code == 200
    assert response.json == {
        "saved": True,
        "credentialRef": "lab-ws-01",
        "hosts": 4,
    }
    assert calls == [("  LAB-WS-01 ", " .\\LabGatewaySvc ", "secret-password")]
    assert "secret-password" not in response.get_data(as_text=True)


def test_winrm_credentials_route_contract_maps_validation_errors_to_400(client, monkeypatch):
    save = Mock(side_effect=ValueError("password is required"))
    reload_hosts = Mock()
    monkeypatch.setattr(worker, "save_winrm_credentials", save)
    monkeypatch.setattr(worker, "reload_hosts", reload_hosts)

    response = client.post(
        "/api/hosts/winrm-credentials",
        json={"credentialRef": "lab-ws-01", "user": "svc", "password": ""},
    )

    assert response.status_code == 400
    assert response.json == {"error": "Invalid WinRM credentials request"}
    reload_hosts.assert_not_called()


def test_winrm_credentials_route_contract_hides_storage_errors(client, monkeypatch):
    monkeypatch.setattr(
        worker,
        "save_winrm_credentials",
        Mock(side_effect=RuntimeError("secret credential storage details")),
    )

    response = client.post(
        "/api/hosts/winrm-credentials",
        json={"credentialRef": "lab-ws-01", "user": "svc", "password": "secret-password"},
        headers={"X-Request-ID": "credentials-1"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "credentials-1",
    }
    assert "secret credential storage details" not in response.get_data(as_text=True)
    assert "secret-password" not in response.get_data(as_text=True)


def test_winrm_credentials_route_contract_maps_reload_failure_to_500(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        worker,
        "save_winrm_credentials",
        lambda credential_ref, user, password: calls.append((credential_ref, user, password)),
    )
    monkeypatch.setattr(worker, "reload_hosts", lambda: (4, "invalid hosts catalog"))

    response = client.post(
        "/api/hosts/winrm-credentials",
        json={"credentialRef": "lab-ws-01", "user": "svc", "password": "secret-password"},
    )

    assert response.status_code == 500
    assert response.json == {"error": "Hosts configuration reload failed"}
    assert calls == [("lab-ws-01", "svc", "secret-password")]
    assert "secret-password" not in response.get_data(as_text=True)
