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
