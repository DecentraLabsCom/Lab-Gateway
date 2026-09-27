from datetime import datetime, timedelta, timezone

import pytest

from wake_ops_service import (
    DEFAULT_WAKE_OPS_DAY_OF_WEEK,
    DEFAULT_WAKE_OPS_HOUR,
    DEFAULT_WAKE_OPS_MINUTE,
    WakeOpsValidationError,
    execute_wake_ops_cycle,
    is_schedule_due,
    normalize_schedule,
    scheduled_occurrence,
)


NOW = datetime(2026, 9, 27, 6, 5, tzinfo=timezone.utc)


def test_normalize_schedule_defaults_to_sunday_at_eight_and_rejects_invalid_timezone():
    result = normalize_schedule({}, default_timezone="Europe/Madrid")

    assert result == {
        "enabled": True,
        "dayOfWeek": DEFAULT_WAKE_OPS_DAY_OF_WEEK,
        "hour": DEFAULT_WAKE_OPS_HOUR,
        "minute": DEFAULT_WAKE_OPS_MINUTE,
        "timezone": "Europe/Madrid",
    }

    with pytest.raises(WakeOpsValidationError):
        normalize_schedule({"timezone": "../../etc/passwd"}, default_timezone="UTC")


def test_scheduled_occurrence_uses_the_configured_local_timezone():
    schedule = normalize_schedule(
        {"dayOfWeek": 6, "hour": 8, "minute": 0, "timezone": "Europe/Madrid"},
        default_timezone="UTC",
    )

    occurrence = scheduled_occurrence(NOW, schedule)

    assert occurrence == datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
    assert is_schedule_due(NOW, schedule, last_scheduled_at=None) is True
    assert is_schedule_due(
        NOW + timedelta(minutes=1),
        schedule,
        last_scheduled_at=occurrence,
    ) is False


def test_wake_ops_cycle_shuts_down_before_wake_when_station_is_on():
    calls = []

    result = execute_wake_ops_cycle(
        {"name": "lab-ws-01"},
        "wake-ops:weekly:1",
        initial_power_state="on",
        shutdown=lambda phase: calls.append(("shutdown", phase)) or True,
        wait_until_off=lambda: calls.append(("wait",)) or True,
        wake=lambda: calls.append(("wake",)) or True,
        now=lambda: NOW,
    )

    assert result["success"] is True
    assert result["initialPowerState"] == "on"
    assert calls == [("shutdown", "before"), ("wait",), ("wake",)]


def test_wake_ops_cycle_restores_off_state_after_successful_wake():
    calls = []

    result = execute_wake_ops_cycle(
        {"name": "lab-ws-01"},
        "wake-ops:weekly:2",
        initial_power_state="off",
        shutdown=lambda phase: calls.append(("shutdown", phase)) or True,
        wait_until_off=lambda: True,
        wake=lambda: calls.append(("wake",)) or True,
        now=lambda: NOW,
    )

    assert result["success"] is True
    assert calls == [("wake",), ("shutdown", "after")]


def test_wake_ops_cycle_does_not_wake_if_the_initial_shutdown_did_not_complete():
    calls = []

    result = execute_wake_ops_cycle(
        {"name": "lab-ws-01"},
        "wake-ops:weekly:3",
        initial_power_state="on",
        shutdown=lambda phase: calls.append(("shutdown", phase)) or False,
        wait_until_off=lambda: pytest.fail("must not wait after failed shutdown"),
        wake=lambda: pytest.fail("must not wake after failed shutdown"),
        now=lambda: NOW,
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert calls == [("shutdown", "before")]


def test_wake_ops_cycle_rejects_unknown_initial_power_state():
    with pytest.raises(WakeOpsValidationError):
        execute_wake_ops_cycle(
            {"name": "lab-ws-01"},
            "wake-ops:weekly:4",
            initial_power_state="unknown",
            shutdown=lambda _phase: True,
            wait_until_off=lambda: True,
            wake=lambda: True,
            now=lambda: NOW,
        )
