from unittest.mock import Mock

import worker


def _host():
    return {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }


def test_winrm_route_contract_requires_host_and_command(client, monkeypatch):
    run_command = Mock()
    monkeypatch.setattr(worker, "run_labstation_command", run_command)

    response = client.post("/api/winrm", json={})

    assert response.status_code == 400
    assert response.json == {"error": "host and command are required"}
    run_command.assert_not_called()


def test_winrm_route_contract_rejects_command_before_host_lookup(client, monkeypatch):
    find_host = Mock()
    run_command = Mock()
    monkeypatch.setattr(worker.HOSTS, "get", find_host)
    monkeypatch.setattr(worker, "run_labstation_command", run_command)

    response = client.post(
        "/api/winrm",
        json={"host": "lab-ws-01", "command": "not-allowed"},
    )

    assert response.status_code == 400
    assert response.json == {"error": "command 'not-allowed' not allowed"}
    find_host.assert_not_called()
    run_command.assert_not_called()


def test_winrm_route_contract_returns_not_found_without_execution(client, monkeypatch):
    find_host = Mock(return_value=None)
    run_command = Mock()
    monkeypatch.setattr(worker.HOSTS, "get", find_host)
    monkeypatch.setattr(worker, "run_labstation_command", run_command)

    response = client.post(
        "/api/winrm",
        json={"host": "missing", "command": "status-json"},
    )

    assert response.status_code == 404
    assert response.json == {"error": "host 'missing' not found in config"}
    find_host.assert_called_once_with("missing")
    run_command.assert_not_called()


def test_winrm_route_contract_forwards_command_arguments_and_result(client, monkeypatch):
    host = _host()
    monkeypatch.setattr(worker.HOSTS, "get", Mock(return_value=host))
    run_command = Mock(return_value={"exit_code": 0, "stdout": "ok", "stderr": ""})
    monkeypatch.setattr(worker, "run_labstation_command", run_command)
    payload = {
        "host": "lab-ws-01",
        "command": "status-json",
        "args": ["--compact"],
        "transport": "ntlm",
        "use_ssl": True,
        "port": 5986,
    }

    response = client.post("/api/winrm", json=payload)

    assert response.status_code == 200
    assert response.json == {"exit_code": 0, "stdout": "ok", "stderr": ""}
    run_command.assert_called_once_with(
        host=host,
        command="status-json",
        args=["--compact"],
        user=None,
        password=None,
        transport="ntlm",
        use_ssl=True,
        port=5986,
    )


def test_winrm_route_contract_defaults_optional_arguments(client, monkeypatch):
    host = _host()
    monkeypatch.setattr(worker.HOSTS, "get", Mock(return_value=host))
    run_command = Mock(return_value={"exit_code": 0})
    monkeypatch.setattr(worker, "run_labstation_command", run_command)

    response = client.post(
        "/api/winrm",
        json={"host": "lab-ws-01", "command": "status-json"},
    )

    assert response.status_code == 200
    run_command.assert_called_once_with(
        host=host,
        command="status-json",
        args=[],
        user=None,
        password=None,
        transport=None,
        use_ssl=None,
        port=None,
    )


def test_winrm_route_contract_maps_trust_errors_without_details(client, monkeypatch):
    host = _host()
    monkeypatch.setattr(worker.HOSTS, "get", Mock(return_value=host))
    monkeypatch.setattr(
        worker,
        "run_labstation_command",
        Mock(side_effect=worker.WinRMTrustError("WINRM_TRUST_INVALID", "secret details")),
    )

    response = client.post(
        "/api/winrm",
        json={"host": "lab-ws-01", "command": "status-json"},
        headers={"X-Request-ID": "winrm-route-1"},
    )

    assert response.status_code == 409
    assert response.json["code"] == "WINRM_TRUST_INVALID"
    assert response.json["requestId"] == "winrm-route-1"
    assert "secret details" not in response.get_data(as_text=True)


def test_winrm_route_contract_hides_unexpected_errors(client, monkeypatch):
    host = _host()
    monkeypatch.setattr(worker.HOSTS, "get", Mock(return_value=host))
    monkeypatch.setattr(
        worker,
        "run_labstation_command",
        Mock(side_effect=RuntimeError("secret command details")),
    )

    response = client.post(
        "/api/winrm",
        json={"host": "lab-ws-01", "command": "status-json"},
        headers={"X-Request-ID": "winrm-route-2"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "winrm-route-2",
    }
    assert "secret command details" not in response.get_data(as_text=True)
