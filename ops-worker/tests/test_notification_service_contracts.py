import json
from datetime import datetime, timezone
from unittest.mock import Mock

from notification_service import (
    check_failure_alert,
    notify_critical_failure,
    send_failure_alert,
    should_send_failure_alert,
)


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _Connection:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        return _Scalar(next(self.results))


class _Begin:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        return _Begin(self.connection)


def test_should_send_failure_alert_preserves_window_queries_and_threshold():
    connection = _Connection([3, None])
    now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)

    result = should_send_failure_alert(
        "lab-ws-01",
        engine=_Engine(connection),
        enabled=True,
        url="https://notify.example/send",
        now=lambda: now,
        failure_threshold=3,
        window_seconds=300,
        cooldown_seconds=900,
        sql_text=lambda value: value,
    )

    assert result is True
    assert len(connection.calls) == 2
    assert "success = 0" in connection.calls[0][0]
    assert connection.calls[0][1]["host"] == "lab-ws-01"
    assert "action = 'alert'" in connection.calls[1][0]


def test_send_failure_alert_preserves_payload_headers_and_operation_projection():
    response = Mock(ok=True, status_code=202, text="accepted")
    post = Mock(return_value=response)
    record = Mock()

    send_failure_alert(
        "reservation-1",
        "lab-1",
        "lab-ws-01",
        "repeated failures",
        {"triggerAction": "wake"},
        recipients=["ops@example.com"],
        url="https://notify.example/send",
        token_header="X-Access-Token",
        token="secret",
        retry_attempts=1,
        retry_backoff_seconds=5,
        http_post=post,
        sleep=Mock(),
        record_operation=record,
        json_dumps=json.dumps,
    )

    post.assert_called_once()
    _, kwargs = post.call_args
    assert kwargs["headers"] == {
        "Content-Type": "application/json",
        "X-Access-Token": "secret",
    }
    assert kwargs["json"]["recipients"] == ["ops@example.com"]
    record.assert_called_once()
    assert record.call_args.args[:6] == (
        "reservation-1",
        "lab-1",
        "lab-ws-01",
        "alert",
        "completed",
        True,
    )


def test_check_failure_alert_forwards_trigger_details_only_when_needed():
    send = Mock()
    check_failure_alert(
        "lab-ws-01",
        "reservation-2",
        "lab-2",
        "wake",
        "offline",
        {"attempts": 2},
        should_send=lambda _host: True,
        failure_threshold=2,
        window_seconds=300,
        send_failure_alert=send,
    )

    send.assert_called_once()
    args = send.call_args.args
    assert args[:3] == ("reservation-2", "lab-2", "lab-ws-01")
    assert args[3] == "At least 2 failed operations in the last 300 seconds"
    assert args[4] == {
        "triggerAction": "wake",
        "triggerMessage": "offline",
        "payload": {"attempts": 2},
    }


def test_notify_critical_failure_records_failed_delivery_without_exception_text():
    post = Mock(side_effect=RuntimeError("private network detail"))
    record = Mock()
    clock = iter([10.0, 10.125])
    logger = Mock()

    notify_critical_failure(
        "reservation-3",
        None,
        "lab-ws-03",
        "wake",
        "offline",
        {"target": "lab-ws-03"},
        enabled=True,
        url="https://notify.example/send",
        recipients=["ops@example.com"],
        token_header="X-Access-Token",
        token="",
        retry_attempts=0,
        retry_backoff_seconds=5,
        http_post=post,
        sleep=Mock(),
        now_seconds=lambda: next(clock),
        record_operation=record,
        json_dumps=json.dumps,
        logger=logger,
    )

    record.assert_called_once()
    assert record.call_args.args[:6] == (
        "reservation-3",
        None,
        "lab-ws-03",
        "notification",
        "failed",
        False,
    )
    assert "private network detail" not in str(record.call_args)
    logger.warning.assert_called_once()
