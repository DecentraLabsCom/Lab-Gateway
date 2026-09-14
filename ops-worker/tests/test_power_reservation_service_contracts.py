from unittest.mock import Mock

from power_reservation_service import (
    execute_reservation_power_phase,
    project_power_operation,
)


def test_project_power_operation_preserves_timeline_shape():
    record_operation = Mock()

    project_power_operation(
        {
            "reservationId": "reservation-1",
            "labId": 42,
            "controllerId": "controller-a",
            "action": "cycle",
            "status": "completed",
            "success": True,
            "durationMs": 12,
            "idempotencyKey": "idempotency-1",
            "actor": "operator",
        },
        record_operation=record_operation,
        logger=Mock(),
    )

    record_operation.assert_called_once()
    kwargs = record_operation.call_args.kwargs
    assert kwargs["reservation_id"] == "reservation-1"
    assert kwargs["lab_id"] == "42"
    assert kwargs["host_name"] == "controller-a"
    assert kwargs["action"] == "power:cycle"
    assert kwargs["response_code"] == 200
    assert kwargs["payload"]["idempotencyKey"] == "idempotency-1"


def test_disabled_power_phase_is_a_successful_noop():
    runtime = Mock()

    result = execute_reservation_power_phase(
        "reservation-1",
        None,
        {"name": "lab-ws-01"},
        "pre_start",
        {"power": True},
        parse_bool=lambda value, default: default if value is None else bool(value),
        power_runtime=runtime,
        power_validation_error_type=RuntimeError,
        host_local_mode=lambda _host: False,
        logger=Mock(),
    )

    assert result == {
        "success": True,
        "status": "power_disabled",
        "phase": "pre_start",
        "steps": [],
    }
    runtime.execute_policy.assert_not_called()
