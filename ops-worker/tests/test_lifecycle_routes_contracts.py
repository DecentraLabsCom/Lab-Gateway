import pytest

import worker


@pytest.mark.parametrize(
    ("path", "handler_name", "payload", "result", "status"),
    [
        (
            "/api/reservations/start",
            "handle_reservation_start",
            {"reservationId": "r-start", "host": "lab-ws-01"},
            {"success": True, "reservationId": "r-start"},
            200,
        ),
        (
            "/api/reservations/end",
            "handle_reservation_end",
            {"reservationId": "r-end", "host": "lab-ws-01"},
            {"success": False, "reservationId": "r-end"},
            502,
        ),
        (
            "/api/demo/start",
            "handle_demo_start",
            {"demoId": "demo:jti", "labId": "42"},
            {"success": True, "operationId": "demo:jti"},
            200,
        ),
        (
            "/api/demo/event",
            "handle_demo_event",
            {"demoId": "demo:jti", "labId": "42", "event": "connected"},
            {"success": True, "event": "connected"},
            200,
        ),
        (
            "/api/demo/end",
            "handle_demo_end",
            {"demoId": "demo:jti", "labId": "42", "reason": "expired"},
            {"success": False, "operationId": "demo:jti"},
            502,
        ),
    ],
)
def test_lifecycle_route_contract_forwards_payload_result_and_status(
    client,
    monkeypatch,
    path,
    handler_name,
    payload,
    result,
    status,
):
    calls = []

    def fake_handler(received_payload):
        calls.append(received_payload)
        return result, status

    monkeypatch.setattr(worker, handler_name, fake_handler)

    response = client.post(path, json=payload)

    assert response.status_code == status
    assert response.json == result
    assert calls == [payload]


@pytest.mark.parametrize(
    ("path", "handler_name"),
    [
        ("/api/reservations/start", "handle_reservation_start"),
        ("/api/reservations/end", "handle_reservation_end"),
        ("/api/demo/start", "handle_demo_start"),
        ("/api/demo/event", "handle_demo_event"),
        ("/api/demo/end", "handle_demo_end"),
    ],
)
def test_lifecycle_route_contract_uses_empty_object_for_missing_json(client, monkeypatch, path, handler_name):
    calls = []
    monkeypatch.setattr(
        worker,
        handler_name,
        lambda payload: calls.append(payload) or ({"success": False}, 400),
    )

    response = client.post(path)

    assert response.status_code == 400
    assert response.json == {"success": False}
    assert calls == [{}]
