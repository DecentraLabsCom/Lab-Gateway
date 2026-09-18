from unittest.mock import Mock

import worker


def test_heartbeat_poll_route_contract_requires_host(client):
    response = client.post("/api/heartbeat/poll", json={})

    assert response.status_code == 400
    assert response.json == {"error": "host is required"}


def test_heartbeat_poll_route_contract_returns_not_found_for_unknown_host(client, monkeypatch):
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": []}))

    response = client.post("/api/heartbeat/poll", json={"host": "missing"})

    assert response.status_code == 404
    assert response.json == {"error": "host 'missing' not found in config"}


def test_heartbeat_poll_route_contract_forwards_include_events_and_adds_host(client, monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    calls = []
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(
        worker,
        "poll_heartbeat",
        lambda host_arg, include_events: calls.append((host_arg, include_events))
        or {"heartbeat": {"summary": {"ready": True}}},
    )

    response = client.post(
        "/api/heartbeat/poll",
        json={"host": "lab-ws-01", "include_events": False},
    )

    assert response.status_code == 200
    assert response.json["host"] == "lab-ws-01"
    assert response.json["heartbeat"]["summary"]["ready"] is True
    assert isinstance(response.json["duration_ms"], int)
    assert calls == [(host, False)]


def test_heartbeat_poll_route_contract_maps_trust_errors_to_conflict(client, monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(
        worker,
        "poll_heartbeat",
        Mock(side_effect=worker.WinRMTrustError("WINRM_TLS_FAILED", "secret details")),
    )

    response = client.post("/api/heartbeat/poll", json={"host": "lab-ws-01"})

    assert response.status_code == 409
    assert response.json["error"] == worker.WINRM_TLS_FAILED_MESSAGE
    assert response.json["code"] == "WINRM_TLS_FAILED"
    assert response.json["host"] == "lab-ws-01"
    assert "secret details" not in response.get_data(as_text=True)


def test_heartbeat_poll_route_contract_maps_missing_credentials_to_conflict(client, monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(
        worker,
        "poll_heartbeat",
        Mock(side_effect=ValueError("stored through the credentials endpoint")),
    )
    monkeypatch.setattr(
        worker,
        "is_missing_winrm_credentials_error",
        lambda error: str(error) == "stored through the credentials endpoint",
    )

    response = client.post("/api/heartbeat/poll", json={"host": "lab-ws-01"})

    assert response.status_code == 409
    assert response.json == {
        "error": worker.WINRM_CREDENTIALS_REQUIRED_MESSAGE,
        "code": "WINRM_CREDENTIALS_REQUIRED",
        "host": "lab-ws-01",
    }


def test_heartbeat_poll_route_maps_winrm_network_failure_to_actionable_unavailable(client, monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50", "winrm_port": 5986}
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(
        worker,
        "poll_heartbeat",
        Mock(side_effect=worker.requests.exceptions.ConnectTimeout("station is off")),
    )

    response = client.post("/api/heartbeat/poll", json={"host": "lab-ws-01"})

    assert response.status_code == 503
    assert response.json == {
        "error": worker.WINRM_UNREACHABLE_MESSAGE,
        "code": worker.WINRM_UNREACHABLE_CODE,
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "port": 5986,
    }


def test_heartbeat_poll_route_maps_rejected_credentials_to_actionable_error(client, monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    response_obj = worker.requests.Response()
    response_obj.status_code = 401
    failure = worker.requests.exceptions.HTTPError(response=response_obj)
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(worker, "_request_id", lambda: "heartbeat-auth-1")
    monkeypatch.setattr(worker, "poll_heartbeat", Mock(side_effect=failure))

    response = client.post("/api/heartbeat/poll", json={"host": "lab-ws-01"})

    assert response.status_code == 409
    assert response.json == {
        "error": worker.WINRM_AUTH_FAILED_MESSAGE,
        "code": worker.WINRM_AUTH_FAILED_CODE,
        "host": "lab-ws-01",
        "requestId": "heartbeat-auth-1",
    }


def test_heartbeat_poll_route_maps_missing_remote_file_to_actionable_error(client, monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(worker, "_request_id", lambda: "heartbeat-file-1")
    monkeypatch.setattr(
        worker,
        "poll_heartbeat",
        Mock(side_effect=worker.WinRMHeartbeatError(
            worker.WINRM_HEARTBEAT_NOT_FOUND_CODE,
            "remote path details",
        )),
    )

    response = client.post("/api/heartbeat/poll", json={"host": "lab-ws-01"})

    assert response.status_code == 502
    assert response.json == {
        "error": worker.WINRM_HEARTBEAT_NOT_FOUND_MESSAGE,
        "code": worker.WINRM_HEARTBEAT_NOT_FOUND_CODE,
        "host": "lab-ws-01",
        "requestId": "heartbeat-file-1",
    }
    assert "remote path details" not in response.get_data(as_text=True)


def test_heartbeat_poll_route_maps_invalid_heartbeat_to_actionable_error(client, monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(worker, "_request_id", lambda: "heartbeat-json-1")
    monkeypatch.setattr(
        worker,
        "poll_heartbeat",
        Mock(side_effect=worker.WinRMHeartbeatError(
            worker.WINRM_HEARTBEAT_INVALID_CODE,
            "invalid JSON details",
        )),
    )

    response = client.post("/api/heartbeat/poll", json={"host": "lab-ws-01"})

    assert response.status_code == 502
    assert response.json == {
        "error": worker.WINRM_HEARTBEAT_INVALID_MESSAGE,
        "code": worker.WINRM_HEARTBEAT_INVALID_CODE,
        "host": "lab-ws-01",
        "requestId": "heartbeat-json-1",
    }
    assert "invalid JSON details" not in response.get_data(as_text=True)
