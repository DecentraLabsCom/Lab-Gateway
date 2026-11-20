from datetime import datetime, timezone

import worker


def test_manual_shutdown_is_immediate_and_keeps_idle_guard(monkeypatch):
    command_calls = []
    preflight_calls = []
    host = {"name": "station"}

    monkeypatch.setattr(worker, "HOSTS", {"station": host})
    monkeypatch.setattr(worker, "resolve_lab_ids_for_host", lambda _host: ["lab-1"])
    monkeypatch.setattr(
        worker,
        "_wake_ops_cycle_is_safe",
        lambda checked_host: preflight_calls.append(checked_host) or True,
    )
    monkeypatch.setattr(
        worker,
        "perform_command_step",
        lambda *args: command_calls.append(args) or (True, {}),
    )

    result = worker._shutdown_ops_manual_shutdown("station")

    assert result["success"] is True
    assert len(preflight_calls) == 1
    assert command_calls[0][4:] == (
        "power",
        [
            "shutdown",
            "--delay=0",
            "--require-idle",
            "--reason=Lab Manager Shutdown Ops manual request",
        ],
    )


def test_manual_shutdown_is_blocked_when_gateway_cannot_confirm_idle(monkeypatch):
    command_calls = []
    host = {"name": "station"}

    monkeypatch.setattr(worker, "HOSTS", {"station": host})
    monkeypatch.setattr(worker, "resolve_lab_ids_for_host", lambda _host: ["lab-1"])
    monkeypatch.setattr(worker, "_wake_ops_cycle_is_safe", lambda _host: False)
    monkeypatch.setattr(
        worker,
        "perform_command_step",
        lambda *args: command_calls.append(args) or (True, {}),
    )
    monkeypatch.setattr(worker, "record_reservation_operation", lambda *args, **kwargs: None)

    result = worker._shutdown_ops_manual_shutdown("station")

    assert result["status"] == "blocked"
    assert result["success"] is False
    assert command_calls == []


def test_wake_ops_shutdown_uses_zero_delay_and_idle_guard(monkeypatch):
    command_calls = []
    host = {"name": "station"}

    monkeypatch.setattr(worker, "_wake_ops_cycle_is_safe", lambda _host: True)
    monkeypatch.setattr(
        worker,
        "perform_command_step",
        lambda *args: command_calls.append(args) or (True, {}),
    )

    assert worker._wake_ops_shutdown(host, "reservation-1", "weekly", "lab-1") is True

    assert command_calls[0][4:] == (
        "power",
        [
            "shutdown",
            "--delay=0",
            "--require-wake",
            "--require-idle",
            "--reason=Wake Ops weekly verification",
        ],
    )


def test_weekly_shutdown_ops_uses_zero_delay(monkeypatch):
    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    shutdown_calls = []
    schedule = {
        "host": "station",
        "weeklyEnabled": True,
        "dayOfWeek": 4,
        "hour": 12,
        "minute": 0,
        "timezone": "UTC",
    }

    monkeypatch.setattr(worker, "DB_ENGINE", object())
    monkeypatch.setattr(worker, "GATEWAY_TIMEZONE", "UTC")
    monkeypatch.setattr(worker, "HOSTS", {"station": {"name": "station"}})
    monkeypatch.setattr(worker, "_wake_ops_now", lambda: now)
    monkeypatch.setattr(
        worker,
        "_get_shutdown_ops_weekly_schedules_impl",
        lambda *_args, **_kwargs: [schedule],
    )
    monkeypatch.setattr(worker, "is_schedule_due", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(worker, "scheduled_occurrence", lambda *_args, **_kwargs: now)
    monkeypatch.setattr(
        worker,
        "_claim_shutdown_ops_weekly_run_impl",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(worker, "resolve_lab_ids_for_host", lambda _host: ["lab-1"])
    monkeypatch.setattr(worker, "_wake_ops_probe", lambda _host: True)
    monkeypatch.setattr(
        worker,
        "_shutdown_ops_execute",
        lambda _host, _reservation_id, _lab_id, **kwargs: shutdown_calls.append(
            kwargs
        )
        or {"success": True, "status": "completed", "message": "done"},
    )
    monkeypatch.setattr(
        worker,
        "_finish_shutdown_ops_weekly_run_impl",
        lambda *_args, **_kwargs: None,
    )

    worker.run_shutdown_ops()

    assert len(shutdown_calls) == 1
    assert shutdown_calls[0]["delay_seconds"] == 0
