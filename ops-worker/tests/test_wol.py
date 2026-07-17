import os
import sys
from unittest.mock import patch

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


@pytest.fixture(autouse=True)
def host_registry():
    original = worker.HOSTS
    worker.HOSTS = worker.HostRegistry({"hosts": [{
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "mac": "00:11:22:33:44:55",
    }]})
    yield
    worker.HOSTS = original


def test_api_wol_requires_mac(client):
    response = client.post("/api/wol", json={})
    assert response.status_code == 400
    assert "mac is required" in response.get_data(as_text=True)


def test_api_wol_uses_host_mac(client):
    with patch("worker.wol_and_wait", return_value=(True, 1)) as mock_wol:
        response = client.post("/api/wol", json={"host": "lab-ws-01"})
    assert response.status_code == 200
    assert response.json["success"] is True
    assert response.json["attempts_used"] == 1
    mock_wol.assert_called_once()


def test_wol_and_wait_retries():
    with patch("worker.send_magic_packet") as mock_packet, patch(
        "worker.host_is_up", side_effect=[False, True]
    ) as mock_up:
        result, attempts = worker.wol_and_wait(
            "00:11:22:33:44:55",
            None,
            9,
            "192.168.1.50",
            3,
            0,
        )

    assert result is True
    assert attempts == 2
    assert mock_packet.call_count == 2
    assert mock_up.call_count == 2


def test_api_wol_rejects_command_injection_in_ping_target(client):
    with patch("worker.wol_and_wait") as mock_wol:
        response = client.post(
            "/api/wol",
            json={
                "mac": "00:11:22:33:44:55",
                "ping_target": "127.0.0.1; whoami",
            },
        )

    assert response.status_code == 400
    assert "ping_target" in response.get_data(as_text=True)
    mock_wol.assert_not_called()


def test_host_is_up_does_not_open_socket_for_invalid_target():
    with patch("worker.socket.create_connection") as mock_connect:
        assert worker.host_is_up("127.0.0.1 && whoami", 1) is False

    mock_connect.assert_not_called()


def test_host_is_up_rejects_long_repeated_dns_target_without_regex_backtracking():
    with patch("worker.socket.create_connection") as mock_connect:
        assert worker.host_is_up("0." * 127 + "0", 1) is False

    mock_connect.assert_not_called()


def test_host_is_up_probes_configured_winrm_port_without_shell():
    with patch("worker.socket.create_connection") as mock_connect:
        assert worker.host_is_up("lab-ws-01", 1, probe_port=5986) is True

    mock_connect.assert_called_once_with(("lab-ws-01", 5986), timeout=1.0)
