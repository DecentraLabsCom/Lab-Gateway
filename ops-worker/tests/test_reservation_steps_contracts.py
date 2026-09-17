from unittest.mock import Mock

from reservation_steps import perform_command_step, perform_wake_step


def _record_operation():
    return Mock()


def test_wake_rejects_missing_mac_without_network_side_effects():
    wol_and_wait = Mock()
    record_operation = _record_operation()

    success, step = perform_wake_step(
        {"name": "lab-ws-01", "address": "192.0.2.10"},
        "reservation-1",
        "42",
        {},
        wol_and_wait=wol_and_wait,
        record_operation=record_operation,
        notify_failure=Mock(),
        current_epoch=lambda: 100.0,
        logger=Mock(),
    )

    assert success is False
    assert step["message"] == "MAC address not configured"
    wol_and_wait.assert_not_called()
    record_operation.assert_called_once_with(
        "reservation-1",
        "42",
        "lab-ws-01",
        "wake",
        "failed",
        False,
        message="MAC address not configured",
    )


def test_wake_uses_thirty_second_default_wait():
    wol_and_wait = Mock(return_value=(True, 1))
    record_operation = _record_operation()

    success, step = perform_wake_step(
        {
            "name": "lab-ws-01",
            "address": "192.168.1.50",
            "mac": "00:11:22:33:44:55",
        },
        "reservation-1",
        "42",
        {},
        wol_and_wait=wol_and_wait,
        record_operation=record_operation,
        notify_failure=Mock(),
        current_epoch=lambda: 100.0,
        logger=Mock(),
    )

    assert success is True
    assert step["details"]["waitSeconds"] == 30.0
    wol_and_wait.assert_called_once_with(
        "00:11:22:33:44:55",
        None,
        9,
        "192.168.1.50",
        3,
        30.0,
        probe_port=None,
    )


def test_command_preserves_result_summary_and_failure_notification():
    record_operation = _record_operation()
    notify_failure = Mock()
    result = {"exit_code": 7, "stdout": "out\n", "stderr": "err\n", "duration_ms": 12}

    success, step = perform_command_step(
        {"name": "lab-ws-01"},
        "reservation-1",
        "42",
        "prepare",
        "prepare-session",
        ["--guard-grace=90"],
        run_labstation_command=Mock(return_value=result),
        record_operation=record_operation,
        notify_failure=notify_failure,
        current_epoch=lambda: 100.0,
        logger=Mock(),
    )

    assert success is False
    assert step["details"] == {
        "exitCode": 7,
        "stdout": "out",
        "stderr": "err",
        "args": ["--guard-grace=90"],
        "durationMs": 12,
    }
    notify_failure.assert_called_once()
