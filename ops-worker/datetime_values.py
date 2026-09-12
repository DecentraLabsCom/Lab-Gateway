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
