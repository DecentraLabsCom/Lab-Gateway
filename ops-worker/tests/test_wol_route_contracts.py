from unittest.mock import Mock

import worker


def test_wol_route_contract_requires_mac_before_calling_wol(client, monkeypatch):
    wol_and_wait = Mock()
    monkeypatch.setattr(worker, "wol_and_wait", wol_and_wait)

    response = client.post("/api/wol", json={})

    assert response.status_code == 400
    assert response.json == {"error": "mac is required"}
    wol_and_wait.assert_not_called()


def test_wol_route_contract_forwards_host_defaults_and_returns_result(client, monkeypatch):
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "mac": "00:11:22:33:44:55",
        "broadcast": "192.168.1.255",
        "winrm_port": 5986,
    }
    monkeypatch.setattr(worker.HOSTS, "get", Mock(return_value=host))
    wol_and_wait = Mock(return_value=(True, 2))
    monkeypatch.setattr(worker, "wol_and_wait", wol_and_wait)

    response = client.post("/api/wol", json={"host": "lab-ws-01"})

    assert response.status_code == 200
    assert response.json["success"] is True
    assert response.json["attempts_used"] == 2
    assert response.json["ping_target"] == "192.168.1.50"
    wol_and_wait.assert_called_once_with(
        "00:11:22:33:44:55",
        "192.168.1.255",
        9,
        "192.168.1.50",
        3,
        30.0,
        probe_port=5986,
    )


def test_wol_route_contract_forwards_explicit_values(client, monkeypatch):
    wol_and_wait = Mock(return_value=(False, 3))
    monkeypatch.setattr(worker, "wol_and_wait", wol_and_wait)

    response = client.post(
        "/api/wol",
        json={
            "mac": "00:11:22:33:44:55",
            "broadcast": "192.168.1.255",
            "port": 7,
            "ping_target": "lab-ws-01",
            "attempts": 4,
            "ping_timeout": 1.5,
        },
    )

    assert response.status_code == 200
    assert response.json["success"] is False
    assert response.json["attempts_used"] == 3
    assert response.json["ping_target"] == "lab-ws-01"
    wol_and_wait.assert_called_once_with(
        "00:11:22:33:44:55",
        "192.168.1.255",
        7,
        "lab-ws-01",
        4,
        1.5,
        probe_port=None,
    )


def test_wol_route_contract_rejects_invalid_target_without_calling_wol(client, monkeypatch):
    wol_and_wait = Mock()
    monkeypatch.setattr(worker, "wol_and_wait", wol_and_wait)

    response = client.post(
        "/api/wol",
        json={
            "mac": "00:11:22:33:44:55",
            "ping_target": "127.0.0.1; whoami",
        },
    )

    assert response.status_code == 400
    assert response.json == {"error": "ping_target is invalid"}
    wol_and_wait.assert_not_called()


def test_wol_route_contract_hides_operation_errors(client, monkeypatch):
    monkeypatch.setattr(
        worker,
        "wol_and_wait",
        Mock(side_effect=RuntimeError("secret network details")),
    )

    response = client.post(
        "/api/wol",
        json={
            "mac": "00:11:22:33:44:55",
            "ping_target": "127.0.0.1",
        },
        headers={"X-Request-ID": "wol-route-1"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "wol-route-1",
    }
    assert "secret network details" not in response.get_data(as_text=True)
