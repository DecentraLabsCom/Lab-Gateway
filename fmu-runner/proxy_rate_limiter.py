"""Reservation-scoped rate limiting for proxy artifact downloads."""

import time
from collections import deque
from typing import Any, Callable


def allow_download(
    key: str,
    *,
    limit_per_minute: int,
    hits: dict[str, deque[float]],
    lock: Any,
    clock: Callable[[], float] = time.time,
) -> bool:
    """Return whether a download fits in the current rolling one-minute window."""
    if limit_per_minute <= 0:
        return False

    now = clock()
    with lock:
        bucket = hits[key]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= limit_per_minute:
            return False
        bucket.append(now)
        return True


__all__ = ["allow_download"]
