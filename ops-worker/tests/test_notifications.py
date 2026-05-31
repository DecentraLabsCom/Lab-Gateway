import os
import sys
from unittest.mock import Mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def test_parse_recipients_comma_separated_values():
    recipients = worker.parse_recipients("alice@example.com, bob@example.com , , carol@example.com")
    assert recipients == [
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
    ]


def test_notify_critical_failure_sends_expected_payload_and_headers(monkeypatch):
    monkeypatch.setattr(worker, "NOTIFICATION_SERVICE_ENABLED", True)
    monkeypatch.setattr(
        worker,
        "NOTIFICATION_SERVICE_URL",
        "http://blockchain-services:8080/billing/admin/notifications/send",
    )
    monkeypatch.setattr(worker, "NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER", "X-Access-Token")
    monkeypatch.setattr(worker, "NOTIFICATION_SERVICE_ACCESS_TOKEN", "super-secret")
    monkeypatch.setattr(worker, "NOTIFICATION_SERVICE_RETRY_ATTEMPTS", 1)
    worker.NOTIFICATION_SERVICE_RECIPIENTS = ["ops@example.com", "support@example.com"]

    mock_post = Mock(return_value=Mock(ok=True, status_code=200, text="ok"))
    mock_record = Mock()
    monkeypatch.setattr(worker.requests, "post", mock_post)
    monkeypatch.setattr(worker, "record_reservation_operation", mock_record)

    worker.notify_critical_failure(
        reservation_id="0xdead",
        lab_id="42",
        host_name="lab-ws-01",
        action="wake",
        failure_reason="timeout",
        details={"pingTarget": "192.168.1.50"},
    )

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == worker.NOTIFICATION_SERVICE_URL
    assert kwargs["headers"]["X-Access-Token"] == "super-secret"

    payload = kwargs["json"]
    assert payload["recipients"] == ["ops@example.com", "support@example.com"]
    assert payload["subject"].startswith("Lab Gateway alert")
    assert "Reservation: 0xdead" in payload["textBody"]
    assert payload["htmlBody"].startswith("<p>")
    assert payload["icsContent"] is None
    assert payload["icsFileName"] is None
    mock_record.assert_called()


def test_repeated_failures_trigger_alert_notification(db_engine, monkeypatch):
    monkeypatch.setattr(worker, "NOTIFICATION_SERVICE_ENABLED", True)
    monkeypatch.setattr(
        worker,
        "NOTIFICATION_SERVICE_URL",
        "http://blockchain-services:8080/billing/admin/notifications/send",
    )
    monkeypatch.setattr(worker, "NOTIFICATION_SERVICE_ACCESS_TOKEN_HEADER", "X-Access-Token")
    monkeypatch.setattr(worker, "NOTIFICATION_SERVICE_ACCESS_TOKEN", "super-secret")
    monkeypatch.setattr(worker, "NOTIFICATION_SERVICE_RETRY_ATTEMPTS", 1)
    monkeypatch.setattr(worker, "OPS_ALERT_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr(worker, "OPS_ALERT_WINDOW_SECONDS", 3600)
    monkeypatch.setattr(worker, "OPS_ALERT_COOLDOWN_SECONDS", 3600)
    worker.NOTIFICATION_SERVICE_RECIPIENTS = ["ops@example.com"]

    mock_post = Mock(return_value=Mock(ok=True, status_code=200, text="ok"))
    monkeypatch.setattr(worker.requests, "post", mock_post)

    worker.record_reservation_operation(
        reservation_id="0x111",
        lab_id="42",
        host_name="lab-ws-01",
        action="wake",
        status="failed",
        success=False,
        message="wake failed",
    )
    worker.record_reservation_operation(
        reservation_id="0x222",
        lab_id="42",
        host_name="lab-ws-01",
        action="prepare",
        status="failed",
        success=False,
        message="prepare failed",
    )

    # Second failure should trigger an alert notification once.
    assert mock_post.call_count == 1

    with db_engine.begin() as conn:
        alert_row = conn.execute(
            worker.text(
                "SELECT action, status, success, message FROM reservation_operations "
                "WHERE host = :host AND action = 'alert'"
            ),
            {"host": "lab-ws-01"},
        ).mappings().first()

    assert alert_row is not None
    assert alert_row["status"] == "completed"
    assert bool(alert_row["success"]) is True
