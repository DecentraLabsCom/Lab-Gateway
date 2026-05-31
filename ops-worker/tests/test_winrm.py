import os
import sys
from unittest.mock import patch

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
