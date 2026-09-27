"""Database persistence for per-host Wake Ops schedules and outcomes."""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Dict, Optional

from wake_ops_service import normalize_schedule


def _row(result: Any) -> Optional[Mapping[str, Any]]:
    rows = result.mappings().all()
    return rows[0] if rows else None


def _schedule_from_row(
    row: Optional[Mapping[str, Any]],
    *,
    default_timezone: str,
) -> Dict[str, Any]:
    if not row:
        return normalize_schedule({}, default_timezone=default_timezone)
    schedule = normalize_schedule(
        {
            "enabled": row.get("enabled"),
            "dayOfWeek": row.get("day_of_week"),
            "hour": row.get("hour"),
            "minute": row.get("minute"),
            "timezone": row.get("timezone"),
        },
        default_timezone=default_timezone,
    )
    schedule.update(
        {
            "lastScheduledAt": row.get("last_scheduled_at"),
            "lastStartedAt": row.get("last_started_at"),
            "lastFinishedAt": row.get("last_finished_at"),
            "lastStatus": row.get("last_status"),
            "lastMessage": row.get("last_message"),
            "lastInitialPowerState": row.get("last_initial_power_state"),
        }
    )
    return schedule


def get_schedule(
    engine: Any,
    host_name: str,
    *,
    default_timezone: str,
    sql_text: Callable[[str], Any],
) -> Dict[str, Any]:
    if not engine:
        return _schedule_from_row(None, default_timezone=default_timezone)
    with engine.connect() as connection:
        result = connection.execute(
            sql_text(
                """
                SELECT enabled, day_of_week, hour, minute, timezone,
                       last_scheduled_at, last_started_at, last_finished_at,
                       last_status, last_message, last_initial_power_state
                  FROM wake_ops_schedules
                 WHERE host = :host
                """
            ),
            {"host": host_name},
        )
        return _schedule_from_row(_row(result), default_timezone=default_timezone)


def save_schedule(
    engine: Any,
    host_name: str,
    schedule: Mapping[str, Any],
    *,
    sql_text: Callable[[str], Any],
    now: Callable[[], datetime],
    last_scheduled_at: Any = None,
    last_started_at: Any = None,
    last_finished_at: Any = None,
    last_status: Optional[str] = None,
    last_message: Optional[str] = None,
    last_initial_power_state: Optional[str] = None,
) -> Dict[str, Any]:
    if not engine:
        raise RuntimeError("Wake Ops persistence requires a database")
    normalized = normalize_schedule(schedule)
    values = {
        "host": host_name,
        "enabled": normalized["enabled"],
        "day_of_week": normalized["dayOfWeek"],
        "hour": normalized["hour"],
        "minute": normalized["minute"],
        "timezone": normalized["timezone"],
        "last_scheduled_at": last_scheduled_at,
        "last_started_at": last_started_at,
        "last_finished_at": last_finished_at,
        "last_status": last_status,
        "last_message": last_message,
        "last_initial_power_state": last_initial_power_state,
        "updated_at": now(),
        "created_at": now(),
    }
    with engine.begin() as connection:
        result = connection.execute(
            sql_text(
                """
                UPDATE wake_ops_schedules
                   SET enabled = :enabled,
                       day_of_week = :day_of_week,
                       hour = :hour,
                       minute = :minute,
                       timezone = :timezone,
                       last_scheduled_at = :last_scheduled_at,
                       last_started_at = :last_started_at,
                       last_finished_at = :last_finished_at,
                       last_status = :last_status,
                       last_message = :last_message,
                       last_initial_power_state = :last_initial_power_state,
                       updated_at = :updated_at
                 WHERE host = :host
                """
            ),
            values,
        )
        if not result.rowcount:
            connection.execute(
                sql_text(
                    """
                    INSERT INTO wake_ops_schedules (
                        host, enabled, day_of_week, hour, minute, timezone,
                        last_scheduled_at, last_started_at, last_finished_at,
                        last_status, last_message, last_initial_power_state,
                        created_at, updated_at
                    ) VALUES (
                        :host, :enabled, :day_of_week, :hour, :minute, :timezone,
                        :last_scheduled_at, :last_started_at, :last_finished_at,
                        :last_status, :last_message, :last_initial_power_state,
                        :created_at, :updated_at
                    )
                    """
                ),
                values,
            )
    saved = dict(normalized)
    saved.update(
        {
            "lastScheduledAt": last_scheduled_at,
            "lastStartedAt": last_started_at,
            "lastFinishedAt": last_finished_at,
            "lastStatus": last_status,
            "lastMessage": last_message,
            "lastInitialPowerState": last_initial_power_state,
        }
    )
    return saved


def latest_wake_operation(
    engine: Any,
    host_name: str,
    *,
    sql_text: Callable[[str], Any],
) -> Optional[Dict[str, Any]]:
    if not engine:
        return None
    with engine.connect() as connection:
        result = connection.execute(
            sql_text(
                """
                SELECT status, success, created_at, message
                  FROM reservation_operations
                 WHERE host = :host AND action = :action
                 ORDER BY created_at DESC, id DESC
                 LIMIT 1
                """
            ),
            {"host": host_name, "action": "wake"},
        )
        row = _row(result)
    if not row:
        return None
    return {
        "status": row.get("status"),
        "success": bool(row.get("success")),
        "createdAt": row.get("created_at"),
        "message": row.get("message"),
    }


__all__ = ["get_schedule", "latest_wake_operation", "save_schedule"]
