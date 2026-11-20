"""Validation and schedule helpers for per-station Shutdown Ops."""

from collections.abc import Mapping
from typing import Any, Dict, Optional

from wake_ops_service import normalize_schedule


def normalize_shutdown_ops_schedule(
    payload: Optional[Mapping[str, Any]],
    *,
    default_timezone: str = "UTC",
) -> Dict[str, Any]:
    values = payload or {}
    weekly_enabled = values.get("weeklyEnabled", values.get("weekly_enabled"))
    reservation_enabled = values.get(
        "afterReservationEnd",
        values.get("after_reservation_end"),
    )
    weekly = normalize_schedule(
        {
            "enabled": False if weekly_enabled is None else weekly_enabled,
            "dayOfWeek": values.get("dayOfWeek", values.get("day_of_week", 6)),
            "hour": values.get("hour", 23),
            "minute": values.get("minute", 0),
            "timezone": values.get("timezone", values.get("time_zone")),
        },
        default_timezone=default_timezone,
    )
    reservation = normalize_schedule(
        {"enabled": False if reservation_enabled is None else reservation_enabled},
        default_timezone=default_timezone,
    )
    return {
        "afterReservationEnd": reservation["enabled"],
        "weeklyEnabled": weekly["enabled"],
        "dayOfWeek": weekly["dayOfWeek"],
        "hour": weekly["hour"],
        "minute": weekly["minute"],
        "timezone": weekly["timezone"],
    }


__all__ = ["normalize_shutdown_ops_schedule"]
