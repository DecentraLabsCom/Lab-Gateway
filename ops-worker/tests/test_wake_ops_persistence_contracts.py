from datetime import datetime, timezone

from sqlalchemy import text

from wake_ops_persistence import get_schedule, latest_wake_operation, save_schedule


def test_wake_ops_schedule_is_durable_and_defaults_to_weekly_sunday(db_engine):
    now = lambda: datetime(2026, 9, 27, 6, tzinfo=timezone.utc)

    initial = get_schedule(
        db_engine,
        "lab-ws-01",
        default_timezone="Europe/Madrid",
        sql_text=text,
    )
    saved = save_schedule(
        db_engine,
        "lab-ws-01",
        {"enabled": False, "dayOfWeek": 1, "hour": 9, "minute": 30, "timezone": "UTC"},
        sql_text=text,
        now=now,
        last_status="disabled",
    )
    loaded = get_schedule(
        db_engine,
        "lab-ws-01",
        default_timezone="Europe/Madrid",
        sql_text=text,
    )

    assert initial["dayOfWeek"] == 6
    assert initial["hour"] == 8
    assert saved["timezone"] == "UTC"
    assert loaded["enabled"] is False
    assert loaded["dayOfWeek"] == 1
    assert loaded["lastStatus"] == "disabled"


def test_latest_wake_operation_is_scoped_to_the_host(db_engine):
    with db_engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO reservation_operations
                (reservation_id, lab_id, host, action, status, success, created_at)
            VALUES ('wake-ops:1', NULL, 'lab-ws-01', 'wake', 'completed', 1,
                    '2026-09-27 06:00:00')
            """
        )

    result = latest_wake_operation(
        db_engine,
        "lab-ws-01",
        sql_text=text,
    )

    assert result["success"] is True
    assert result["status"] == "completed"
