import json
from unittest.mock import Mock

from operation_persistence import record_reservation_operation


class _Connection:
    def __init__(self, calls):
        self.calls = calls

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))


class _Begin:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class _Engine:
    def __init__(self, calls):
        self.calls = calls

    def begin(self):
        return _Begin(_Connection(self.calls))


def _dependencies(engine, check_failure_alert):
    return {
        "engine": engine,
        "now": lambda: "2026-09-14T12:00:00+00:00",
        "sql_text": lambda value: value,
        "json_dumps": json.dumps,
        "check_failure_alert": check_failure_alert,
        "logger": Mock(),
    }


def test_record_reservation_operation_preserves_insert_projection_and_payload():
    calls = []
    alert = Mock()

    record_reservation_operation(
        "reservation-1",
        "lab-1",
        "lab-ws-01",
        "prepare",
        "completed",
        True,
        response_code=200,
        duration_ms=12,
        payload={"step": "prepare"},
        message="ok",
        **_dependencies(_Engine(calls), alert),
    )

    assert len(calls) == 1
    statement, parameters = calls[0]
    assert "INSERT INTO reservation_operations" in statement
    assert parameters == {
        "reservation_id": "reservation-1",
        "lab_id": "lab-1",
        "host": "lab-ws-01",
        "action": "prepare",
        "status": "completed",
        "success": True,
        "response_code": 200,
        "duration_ms": 12,
        "payload": '{"step": "prepare"}',
        "message": "ok",
        "created_at": "2026-09-14T12:00:00+00:00",
    }
    alert.assert_not_called()


def test_record_reservation_operation_checks_alerts_only_for_non_alert_failures():
    calls = []
    alert = Mock()
    dependencies = _dependencies(_Engine(calls), alert)

    record_reservation_operation(
        "reservation-2",
        None,
        "lab-ws-02\nunsafe",
        "wake",
        "failed",
        False,
        message="offline",
        **dependencies,
    )

    alert.assert_called_once_with(
        "lab-ws-02\nunsafe",
        "reservation-2",
        None,
        "wake",
        "offline",
        None,
    )

    alert.reset_mock()
    record_reservation_operation(
        "reservation-2",
        None,
        "lab-ws-02",
        "alert",
        "failed",
        False,
        **dependencies,
    )
    alert.assert_not_called()


def test_record_reservation_operation_is_noop_without_an_operations_engine():
    alert = Mock()
    record_reservation_operation(
        "reservation-3",
        None,
        "lab-ws-03",
        "wake",
        "failed",
        False,
        engine=None,
        now=Mock(),
        sql_text=Mock(),
        json_dumps=Mock(),
        check_failure_alert=alert,
        logger=Mock(),
    )
    alert.assert_not_called()
