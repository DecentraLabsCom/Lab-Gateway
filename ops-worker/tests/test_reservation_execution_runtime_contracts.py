from dataclasses import FrozenInstanceError, replace

import pytest

from reservation_execution_context import ReservationExecutionContext
from reservation_execution_runtime import (
    ReservationExecutionRuntime,
    create_reservation_execution_runtime,
)


def _context(*, calls=None, **overrides):
    calls = calls if calls is not None else []
    values = {
        "record_reservation_operation_impl": lambda *args, **kwargs: calls.append(
            ("record", args, kwargs)
        ) or "recorded",
        "get_db_engine": lambda: "ops-db",
        "get_now_utc": lambda: lambda: "now",
        "get_sql_text": lambda: "sql-text",
        "get_json_dumps": lambda: "json-dumps",
        "get_check_failure_alert": lambda: lambda *args, **kwargs: None,
        "check_failure_alert_impl": lambda *args, **kwargs: None,
        "get_logger": lambda: "logger",
        "get_sanitize_log_value": lambda: "sanitize",
        "project_power_operation_impl": lambda *args, **kwargs: calls.append(
            ("power", args, kwargs)
        ),
        "get_record_reservation_operation": lambda: lambda *args, **kwargs: calls.append(
            ("record-alias", args, kwargs)
        ),
        "host_local_mode_enabled_impl": lambda *args, **kwargs: calls.append(
            ("local", args, kwargs)
        ) or True,
        "get_fetch_latest_heartbeat": lambda: "fetch-heartbeat",
        "get_parse_bool": lambda: "parse-bool",
        "execute_reservation_power_phase_impl": lambda *args, **kwargs: calls.append(
            ("phase", args, kwargs)
        ) or {"success": True},
        "get_power_runtime": lambda: "power-runtime",
        "get_power_validation_error_type": lambda: RuntimeError,
        "get_host_local_mode_enabled": lambda: lambda value: True,
        "should_send_failure_alert_impl": lambda *args, **kwargs: True,
        "get_notification_enabled": lambda: True,
        "get_notification_url": lambda: "https://notify",
        "get_failure_threshold": lambda: 3,
        "get_window_seconds": lambda: 60,
        "get_cooldown_seconds": lambda: 120,
        "get_should_send_failure_alert": lambda: lambda *args, **kwargs: True,
        "send_failure_alert_impl": lambda *args, **kwargs: None,
        "get_send_failure_alert": lambda: lambda *args, **kwargs: None,
        "get_recipients": lambda: ["ops@example.com"],
        "get_token_header": lambda: "Authorization",
        "get_token": lambda: "token",
        "get_retry_attempts": lambda: 2,
        "get_retry_backoff_seconds": lambda: 0.1,
        "get_http_post": lambda: "post",
        "get_sleep": lambda: "sleep",
        "get_current_epoch": lambda: "epoch",
        "notify_critical_failure_impl": lambda *args, **kwargs: None,
        "get_notify_critical_failure": lambda: lambda *args, **kwargs: None,
        "perform_wake_step_impl": lambda *args, **kwargs: (True, {"action": "wake"}),
        "get_wol_and_wait": lambda: "wol",
        "get_run_labstation_command": lambda: "command",
        "perform_command_step_impl": lambda *args, **kwargs: (
            True,
            {"action": "command"},
        ),
    }
    values.update(overrides)
    return ReservationExecutionContext(**values), calls


def test_reservation_execution_runtime_forwards_operation_dependencies():
    context, calls = _context()
    runtime = create_reservation_execution_runtime(context)

    assert isinstance(runtime, ReservationExecutionRuntime)
    assert runtime.record_reservation_operation(
        "reservation-1", "lab-1", "host-1", "wake", "completed", True
    ) == "recorded"
    assert runtime.host_local_mode_enabled({"name": "host-1"}) is True
    assert runtime.execute_reservation_power_phase(
        "reservation-1", "lab-1", {"name": "host-1"}, "pre_start", {}
    ) == {"success": True}

    record = calls[0]
    assert record[0] == "record"
    assert record[1] == (
        "reservation-1",
        "lab-1",
        "host-1",
        "wake",
        "completed",
        True,
        None,
        None,
        None,
        None,
    )
    assert record[2]["engine"] == "ops-db"
    assert record[2]["now"]() == "now"
    assert record[2]["sql_text"] == "sql-text"
    assert record[2]["json_dumps"] == "json-dumps"

    local = calls[1]
    assert local[2]["db_engine"] == "ops-db"
    assert local[2]["fetch_latest_heartbeat"] == "fetch-heartbeat"
    assert local[2]["parse_bool"] == "parse-bool"

    phase = calls[2]
    assert phase[2]["parse_bool"] == "parse-bool"
    assert phase[2]["power_runtime"] == "power-runtime"
    assert phase[2]["power_validation_error_type"] is RuntimeError


def test_reservation_execution_runtime_resolves_mutable_operation_callbacks():
    recorded = []
    context, _calls = _context()
    context = replace(
        context,
        project_power_operation_impl=lambda _operation, *, record_operation, logger: record_operation(
            "id"
        ),
        get_record_reservation_operation=lambda: lambda value: recorded.append(
            ("second", value)
        ),
    )
    runtime = create_reservation_execution_runtime(context)

    runtime.record_power_operation({})

    assert recorded == [("second", "id")]


def test_reservation_execution_context_is_immutable():
    context, _calls = _context()

    with pytest.raises(FrozenInstanceError):
        setattr(context, "get_logger", lambda: "changed")
