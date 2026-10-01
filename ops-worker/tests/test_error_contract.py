from unittest.mock import patch


def test_wol_internal_failure_returns_correlation_id_without_exception_text(client):
    with patch("worker.wol_and_wait", side_effect=RuntimeError("secret socket path")):
        response = client.post(
            "/api/wol",
            json={"mac": "00:11:22:33:44:55", "ping_target": "lab-ws-01"},
            headers={"X-Request-ID": "l01-test-1"},
        )

    assert response.status_code == 500
    payload = response.get_json()
    assert payload == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "l01-test-1",
    }
    assert "secret socket path" not in response.get_data(as_text=True)


def test_internal_error_log_escapes_line_breaks(caplog):
    import logging

    import worker

    with worker.APP.test_request_context("/api/wol"), caplog.at_level(logging.ERROR):
        worker.internal_error_response("bad\r\nforged", RuntimeError("secret"))

    message = next(record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR)
    assert "bad\\r\\nforged" in message
    assert "bad\r\nforged" not in message


def test_winrm_error_response_does_not_expose_exception_text(client, monkeypatch):
    import worker

    monkeypatch.setattr(
        worker,
        "run_labstation_command",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            worker.WinRMTrustError("WINRM_TRUST_INVALID", "secret certificate parser details")
        ),
    )
    original_hosts = worker.HOSTS
    worker.HOSTS = worker.HostRegistry({"hosts": [{"name": "lab-ws-01", "address": "192.168.1.50"}]})
    try:
        response = client.post(
            "/api/winrm",
            json={"host": "lab-ws-01", "command": "status-json"},
        )
    finally:
        worker.HOSTS = original_hosts

    assert response.status_code == 409
    assert response.json["error"] == worker.WINRM_CERTIFICATE_INVALID_MESSAGE
    assert response.json["code"] == "WINRM_TRUST_INVALID"
    assert "secret certificate parser details" not in response.get_data(as_text=True)


def test_heartbeat_winrm_error_response_does_not_expose_exception_text(client, monkeypatch):
    import worker

    monkeypatch.setattr(
        worker,
        "poll_heartbeat",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            worker.WinRMTrustError("WINRM_TLS_FAILED", "secret TLS handshake details")
        ),
    )
    original_hosts = worker.HOSTS
    worker.HOSTS = worker.HostRegistry({"hosts": [{"name": "lab-ws-01", "address": "192.168.1.50"}]})
    try:
        response = client.post(
            "/api/heartbeat/poll",
            json={"host": "lab-ws-01"},
        )
    finally:
        worker.HOSTS = original_hosts

    assert response.status_code == 409
    assert response.json["error"] == worker.WINRM_TLS_FAILED_MESSAGE
    assert response.json["code"] == "WINRM_TLS_FAILED"
    assert "secret TLS handshake details" not in response.get_data(as_text=True)
