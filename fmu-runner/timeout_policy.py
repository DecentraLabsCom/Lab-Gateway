import math
from typing import Optional

from fastapi import HTTPException


def effective_timeout_seconds(
    requested_timeout: int,
    *,
    max_timeout: int,
    exp_ts: Optional[int],
    now: float,
) -> int:
    capped_timeout = min(requested_timeout, max_timeout)
    if exp_ts is None:
        return capped_timeout

    remaining = int(math.ceil(exp_ts - now))
    if remaining <= 0:
        raise HTTPException(status_code=401, detail="Reservation token has expired")
    return min(capped_timeout, remaining)