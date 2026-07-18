import os
import sys
from unittest.mock import patch

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def test_api_winrm_requires_host_and_command(client):
    response = client.post("/api/winrm", json={})
    assert response.status_code == 400
    assert "host and command are required" in response.get_data(as_text=True)


def test_api_winrm_rejects_unauthorized_command(client):
    response = client.post(
        "/api/winrm",
        json={"host": "lab-ws-01", "command": "not-allowed"},
    )
    assert response.status_code == 400
    assert "command 'not-allowed' not allowed" in response.get_data(as_text=True)


def test_api_winrm_returns_host_not_found(client):
    response = client.post(
        "/api/winrm",
        json={"host": "unknown", "command": "status-json"},
    )
    assert response.status_code == 404
    assert "host 'unknown' not found in config" in response.get_data(as_text=True)


@patch("worker.run_labstation_command", return_value={"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 42})
def test_api_winrm_executes_allowed_command(mock_run, client):
    original = worker.HOSTS
    worker.HOSTS = worker.HostRegistry({"hosts": [{
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "winrm_user": "user",
        "winrm_pass": "pass",
    }]})
    try:
        response = client.post(
            "/api/winrm",
            json={"host": "lab-ws-01", "command": "status-json"},
        )
    finally:
        worker.HOSTS = original

    assert response.status_code == 200
    assert response.json["exit_code"] == 0
    assert response.json["stdout"] == "ok"
    mock_run.assert_called_once()


def test_run_labstation_command_requires_credentials():
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    try:
        worker.run_labstation_command(host, "status-json", [], None, None, None, None, None)
        assert False, "Expected ValueError when credentials are missing"
    except ValueError as exc:
        assert "WinRM credentials are required" in str(exc)


def test_winrm_defaults_to_https_and_rejects_plaintext():
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }
    endpoint = worker.winrm_endpoint(host, None, None)
    assert endpoint == "https://192.168.1.50:5986/wsman"
    try:
        worker.winrm_endpoint(host, False, 5985)
        assert False, "Expected plaintext WinRM to be rejected"
    except ValueError as exc:
        assert "HTTPS" in str(exc) or "use_ssl" in str(exc)


def test_winrm_request_cannot_override_host_transport_or_port():
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }
    try:
        worker._winrm_connection_policy(host, True, 5985, "ntlm")
        assert False, "Expected host port policy rejection"
    except ValueError as exc:
        assert "port" in str(exc)
    try:
        worker._winrm_connection_policy(host, True, 5986, "kerberos")
        assert False, "Expected host transport policy rejection"
    except ValueError as exc:
        assert "transport" in str(exc)


def test_winrm_catalog_fails_closed_on_transport_or_management_vlan():
    secure_host = {
        "name": "lab-ws-01",
        "address": "10.7.74.10",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }
    original_cidrs = worker.WINRM_MANAGEMENT_CIDRS
    try:
        worker.WINRM_MANAGEMENT_CIDRS = []
        with pytest.raises(ValueError, match="WINRM_MANAGEMENT_CIDRS"):
            worker.validate_winrm_catalog({"hosts": [secure_host]})

        worker.WINRM_MANAGEMENT_CIDRS = ["10.7.74.0/24"]
        worker.validate_winrm_catalog({"hosts": [secure_host]})

        insecure_host = {**secure_host, "winrm_use_ssl": False, "winrm_port": 5985}
        with pytest.raises(ValueError, match="HTTPS"):
            worker.validate_winrm_catalog({"hosts": [insecure_host]})

        outside_host = {**secure_host, "address": "10.7.75.10"}
        with pytest.raises(ValueError, match="WINRM_MANAGEMENT_CIDRS"):
            worker.validate_winrm_catalog({"hosts": [outside_host]})
    finally:
        worker.WINRM_MANAGEMENT_CIDRS = original_cidrs
