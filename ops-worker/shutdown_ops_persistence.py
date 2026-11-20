"""Database persistence for per-station Shutdown Ops settings and runs."""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Dict, List, Optional

from shutdown_ops_service import normalize_shutdown_ops_schedule


def _row(result: Any) -> Optional[Mapping[str, Any]]:
    rows = result.mappings().all()
    return rows[0] if rows else None


def _schedule(row: Optional[Mapping[str, Any]], default_timezone: str) -> Dict[str, Any]:
    if not row:
        return normalize_shutdown_ops_schedule({}, default_timezone=default_timezone)
    result = normalize_shutdown_ops_schedule(
        {
            "afterReservationEnd": row.get("after_reservation_end"),
            "weeklyEnabled": row.get("weekly_enabled"),
            "dayOfWeek": row.get("day_of_week"),
            "hour": row.get("hour"),
            "minute": row.get("minute"),
            "timezone": row.get("timezone"),
        },
        default_timezone=default_timezone,
    )
    result.update(
        {
            "lastScheduledAt": row.get("last_scheduled_at"),
            "lastStartedAt": row.get("last_started_at"),
            "lastFinishedAt": row.get("last_finished_at"),
            "lastStatus": row.get("last_status"),
            "lastMessage": row.get("last_message"),
        }
    )
    return result


def get_schedule(
    engine: Any,
    host_name: str,
    *,
    default_timezone: str,
    sql_text: Callable[[str], Any],
) -> Dict[str, Any]:
    if not engine:
        return _schedule(None, default_timezone)
    with engine.connect() as connection:
        result = connection.execute(
            sql_text(
                """
                SELECT after_reservation_end, weekly_enabled, day_of_week, hour,
                       minute, timezone, last_scheduled_at, last_started_at,
                       last_finished_at, last_status, last_message
                  FROM shutdown_ops_schedules
                 WHERE host = :host
                """
            ),
            {"host": host_name},
        )
        return _schedule(_row(result), default_timezone)


def save_schedule(
    engine: Any,
    host_name: str,
    schedule: Mapping[str, Any],
    *,
    default_timezone: str,
    sql_text: Callable[[str], Any],
    now: Callable[[], datetime],
    reset_weekly_occurrence: bool = False,
    weekly_baseline: Optional[datetime] = None,
) -> Dict[str, Any]:
    if not engine:
        raise RuntimeError("Shutdown Ops persistence requires a database")
    normalized = normalize_shutdown_ops_schedule(schedule, default_timezone=default_timezone)
    values = {
        "host": host_name,
        "after_reservation_end": normalized["afterReservationEnd"],
        "weekly_enabled": normalized["weeklyEnabled"],
        "day_of_week": normalized["dayOfWeek"],
        "hour": normalized["hour"],
        "minute": normalized["minute"],
        "timezone": normalized["timezone"],
        "now": now(),
        "reset_weekly_occurrence": reset_weekly_occurrence,
        "weekly_baseline": weekly_baseline,
    }
    with engine.begin() as connection:
        connection.execute(
            sql_text(
                """
                INSERT INTO shutdown_ops_schedules (
                    host, after_reservation_end, weekly_enabled, day_of_week,
                    hour, minute, timezone, last_scheduled_at, created_at, updated_at
                ) VALUES (
                    :host, :after_reservation_end, :weekly_enabled, :day_of_week,
                    :hour, :minute, :timezone, :weekly_baseline, :now, :now
                )
                ON DUPLICATE KEY UPDATE
                    after_reservation_end = :after_reservation_end,
                    weekly_enabled = :weekly_enabled,
                    day_of_week = :day_of_week,
                    hour = :hour,
                    minute = :minute,
                    timezone = :timezone,
                    last_scheduled_at = CASE
                        WHEN :reset_weekly_occurrence THEN :weekly_baseline
                        ELSE last_scheduled_at
                    END,
                    last_started_at = CASE
                        WHEN :reset_weekly_occurrence THEN NULL
                        ELSE last_started_at
                    END,
                    last_finished_at = CASE
                        WHEN :reset_weekly_occurrence THEN NULL
                        ELSE last_finished_at
                    END,
                    last_status = CASE
                        WHEN :reset_weekly_occurrence THEN NULL
                        ELSE last_status
                    END,
                    last_message = CASE
                        WHEN :reset_weekly_occurrence THEN NULL
                        ELSE last_message
                    END,
                    updated_at = :now
                """
            ),
            values,
        )
    return normalized


def enabled_weekly_schedules(
    engine: Any,
    *,
    default_timezone: str,
    sql_text: Callable[[str], Any],
) -> List[Dict[str, Any]]:
    if not engine:
        return []
    with engine.connect() as connection:
        result = connection.execute(
            sql_text(
                """
                SELECT host, after_reservation_end, weekly_enabled, day_of_week,
                       hour, minute, timezone, last_scheduled_at, last_started_at,
                       last_finished_at, last_status, last_message
                  FROM shutdown_ops_schedules
                 WHERE weekly_enabled = TRUE
                """
            )
        )
        return [
            {"host": row.get("host"), **_schedule(row, default_timezone)}
            for row in result.mappings().all()
        ]


def claim_weekly_run(
    engine: Any,
    host_name: str,
    occurrence: datetime,
    started_at: datetime,
    *,
    sql_text: Callable[[str], Any],
) -> bool:
    if not engine:
        return False
    with engine.begin() as connection:
        result = connection.execute(
            sql_text(
                """
                UPDATE shutdown_ops_schedules
                   SET last_scheduled_at = :occurrence,
                       last_started_at = :started_at,
                       last_status = 'running',
                       last_message = NULL
                 WHERE host = :host AND weekly_enabled = TRUE
                   AND (last_scheduled_at IS NULL OR last_scheduled_at < :occurrence)
                """
            ),
            {"host": host_name, "occurrence": occurrence, "started_at": started_at},
        )
        return bool(result.rowcount)


def finish_weekly_run(
    engine: Any,
    host_name: str,
    occurrence: datetime,
    finished_at: datetime,
    status: str,
    message: Optional[str],
    *,
    sql_text: Callable[[str], Any],
) -> None:
    if not engine:
        return
    with engine.begin() as connection:
        connection.execute(
            sql_text(
                """
                UPDATE shutdown_ops_schedules
                   SET last_finished_at = :finished_at,
                       last_status = :status,
                       last_message = :message
                 WHERE host = :host AND last_scheduled_at = :occurrence
                """
            ),
            {
                "host": host_name,
                "occurrence": occurrence,
                "finished_at": finished_at,
                "status": status,
                "message": message,
            },
        )


__all__ = [
    "claim_weekly_run",
    "enabled_weekly_schedules",
    "finish_weekly_run",
    "get_schedule",
    "save_schedule",
]
