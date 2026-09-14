"""Pure timestamp normalization helpers."""

from collections.abc import Callable
from datetime import datetime, tzinfo
from typing import Any, Optional


def to_utc(
    value: Any,
    *,
    parse_datetime: Callable[[str], datetime],
    utc_timezone: tzinfo,
) -> Optional[datetime]:
    """Parse a timestamp and normalize it to an aware UTC datetime."""
    if not value:
        return None
    try:
        parsed = parse_datetime(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=utc_timezone)
        return parsed.astimezone(utc_timezone)
    except Exception:  # pylint: disable=broad-except
        return None


def as_utc_datetime(
    value: Any,
    *,
    parse_datetime: Callable[[str], datetime],
    utc_timezone: tzinfo,
) -> Optional[datetime]:
    """Normalize datetime instances and ISO strings to aware UTC values."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = parse_datetime(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=utc_timezone)
    return parsed.astimezone(utc_timezone)


def to_iso(
    value: Any,
    *,
    parse_datetime: Callable[[str], datetime],
    utc_timezone: tzinfo,
) -> Optional[str]:
    """Format a timestamp-like value as an ISO UTC string."""
    if not value:
        return None
    if isinstance(value, str):
        try:
            parsed = parse_datetime(value)
        except ValueError:
            return value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=utc_timezone)
        return parsed.astimezone(utc_timezone).isoformat()
    if value.tzinfo is None:
        return value.replace(tzinfo=utc_timezone).isoformat()
    return value.astimezone(utc_timezone).isoformat()


__all__ = ["as_utc_datetime", "to_iso", "to_utc"]
