from types import SimpleNamespace

from reservation_execution_runtime import (
    ReservationExecutionRuntime,
    create_reservation_execution_runtime,
)


def test_reservation_execution_runtime_forwards_operation_dependencies():
    calls = []
    providers = {
        "_record_reservation_operation_impl": lambda *args, **kwargs: calls.append(
            ("record", args, kwargs)
        ) or "recorded",
        "DB_ENGINE": "ops-db",
        "_now_utc": lambda: "now",
        "text": "sql-text",
        "json": SimpleNamespace(dumps="json-dumps"),
        "_check_failure_alert": lambda *args, **kwargs: None,
        "logging": "logger",
        "_sanitize_log_value": "sanitize",
        "_project_power_operation_impl": lambda *args, **kwargs: calls.append(
            ("power", args, kwargs)
        ),
        "_host_local_mode_enabled_impl": lambda *args, **kwargs: calls.append(
            ("local", args, kwargs)
        ) or True,
        "_fetch_latest_heartbeat": "fetch-heartbeat",
        "parse_bool": "parse-bool",
        "_execute_reservation_power_phase_impl": lambda *args, **kwargs: calls.append(
            ("phase", args, kwargs)
        ) or {"success": True},
        "POWER_RUNTIME": "power-runtime",
        "PowerValidationError": RuntimeError,
    }
    runtime = create_reservation_execution_runtime(providers)

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
    assert record[1] == ("reservation-1", "lab-1", "host-1", "wake", "completed", True, None, None, None, None)
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
    providers = {
        "_project_power_operation_impl": lambda _operation, *, record_operation, logger: record_operation(
            "id"
        ),
        "record_reservation_operation": lambda value: recorded.append(("first", value)),
        "logging": None,
    }
    runtime = create_reservation_execution_runtime(providers)
    providers["record_reservation_operation"] = lambda value: recorded.append(("second", value))

    runtime.record_power_operation({})

    assert recorded == [("second", "id")]
