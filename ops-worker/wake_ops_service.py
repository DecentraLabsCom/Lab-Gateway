"""Pure scheduling and execution rules for weekly Wake Ops verification."""

from collections.abc import Callable, Mapping
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_WAKE_OPS_DAY_OF_WEEK = 6  # Python's Sunday value.
DEFAULT_WAKE_OPS_HOUR = 8
DEFAULT_WAKE_OPS_MINUTE = 0
DEFAULT_GATEWAY_TIMEZONE = "UTC"
WAKE_EVIDENCE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
WAKE_OPS_FIRST_RUN_GRACE_SECONDS = 15 * 60


class WakeOpsValidationError(ValueError):
    """Raised when a Wake Ops schedule or execution state is invalid."""


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise WakeOpsValidationError("enabled must be a boolean")


def _as_int(value: Any, name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise WakeOpsValidationError(f"{name} must be an integer") from exc
    if not minimum <= result <= maximum:
        raise WakeOpsValidationError(f"{name} must be between {minimum} and {maximum}")
    return result


def validate_timezone(value: Any, default: str = DEFAULT_GATEWAY_TIMEZONE) -> str:
    name = str(value or default).strip()
    if not name or len(name) > 64 or name.startswith("/") or ".." in name:
        raise WakeOpsValidationError("timezone is invalid")
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise WakeOpsValidationError("timezone is not available on the gateway") from exc
    return name


def normalize_schedule(
    payload: Optional[Mapping[str, Any]],
    *,
    default_timezone: str = DEFAULT_GATEWAY_TIMEZONE,
) -> Dict[str, Any]:
    values = payload or {}
    return {
        "enabled": _as_bool(values.get("enabled"), True),
        "dayOfWeek": _as_int(
            values.get("dayOfWeek", values.get("day_of_week")),
            "dayOfWeek",
            DEFAULT_WAKE_OPS_DAY_OF_WEEK,
            0,
            6,
        ),
        "hour": _as_int(values.get("hour"), "hour", DEFAULT_WAKE_OPS_HOUR, 0, 23),
        "minute": _as_int(values.get("minute"), "minute", DEFAULT_WAKE_OPS_MINUTE, 0, 59),
        "timezone": validate_timezone(
            values.get("timezone", values.get("time_zone")),
            default_timezone,
        ),
    }


def _aware_utc(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def scheduled_occurrence(now: datetime, schedule: Mapping[str, Any]) -> datetime:
    current = _aware_utc(now)
    if current is None:
        raise WakeOpsValidationError("now must be a datetime")
    zone = ZoneInfo(validate_timezone(schedule.get("timezone")))
    local_now = current.astimezone(zone)
    target_day = int(schedule.get("dayOfWeek", DEFAULT_WAKE_OPS_DAY_OF_WEEK))
    target_time = time(
        int(schedule.get("hour", DEFAULT_WAKE_OPS_HOUR)),
        int(schedule.get("minute", DEFAULT_WAKE_OPS_MINUTE)),
    )
    days_since_target = (local_now.weekday() - target_day) % 7
    target_date = local_now.date() - timedelta(days=days_since_target)
    occurrence = datetime.combine(target_date, target_time, tzinfo=zone)
    if occurrence > local_now:
        occurrence -= timedelta(days=7)
    return occurrence.astimezone(timezone.utc)


def is_schedule_due(
    now: datetime,
    schedule: Mapping[str, Any],
    *,
    last_scheduled_at: Any,
    first_run_grace_seconds: int = WAKE_OPS_FIRST_RUN_GRACE_SECONDS,
) -> bool:
    if not bool(schedule.get("enabled", True)):
        return False
    current = _aware_utc(now)
    occurrence = scheduled_occurrence(current, schedule)
    last = _aware_utc(last_scheduled_at)
    if last is None:
        return (
            current >= occurrence
            and current <= occurrence + timedelta(seconds=max(0, first_run_grace_seconds))
        )
    return current >= occurrence and last < occurrence


def execute_wake_ops_cycle(
    host: Mapping[str, Any],
    reservation_id: str,
    *,
    initial_power_state: str,
    shutdown: Callable[[str], bool],
    wait_until_off: Callable[[], bool],
    wake: Callable[[], bool],
    now: Callable[[], datetime],
) -> Dict[str, Any]:
    """Run the bounded weekly cycle after power state has been classified.

    The caller is responsible for the conservative state classification.  A
    failed pre-shutdown never proceeds to WoL, while a failed post-WoL
    shutdown is reported as a partial failure because the successful wake
    evidence is still useful and remains in the operation timeline.
    """
    if initial_power_state not in {"on", "off"}:
        raise WakeOpsValidationError("initial_power_state must be on or off")

    started_at = now()
    result: Dict[str, Any] = {
        "host": host.get("name", ""),
        "reservationId": reservation_id,
        "initialPowerState": initial_power_state,
        "startedAt": started_at.isoformat() if isinstance(started_at, datetime) else started_at,
        "success": False,
        "status": "failed",
    }

    if initial_power_state == "on":
        if not shutdown("before"):
            result["message"] = "Initial shutdown did not complete; WoL was not sent"
            return result
        if not wait_until_off():
            result["message"] = "Station did not become unreachable after initial shutdown"
            return result

    if not wake():
        result["message"] = "Wake operation failed"
        return result

    if initial_power_state == "off" and not shutdown("after"):
        result.update(
            {
                "status": "partial",
                "message": "WoL succeeded but restoring the initial off state failed",
            }
        )
        return result

    result.update({"success": True, "status": "completed", "message": "Wake Ops completed"})
    return result


__all__ = [
    "DEFAULT_WAKE_OPS_DAY_OF_WEEK",
    "DEFAULT_WAKE_OPS_HOUR",
    "DEFAULT_WAKE_OPS_MINUTE",
    "DEFAULT_GATEWAY_TIMEZONE",
    "WAKE_EVIDENCE_MAX_AGE_SECONDS",
    "WakeOpsValidationError",
    "execute_wake_ops_cycle",
    "is_schedule_due",
    "normalize_schedule",
    "scheduled_occurrence",
    "validate_timezone",
]
