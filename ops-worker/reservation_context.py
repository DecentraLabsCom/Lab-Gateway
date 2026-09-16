"""Explicit dependencies for reservation orchestration construction."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class ReservationRuntimeContext:
    """Live providers used to construct the reservation orchestrator."""

    get_parse_bool: Callable[[], Callable[..., bool]]
    get_env: Callable[[], Callable[..., Any]]
    get_env_or_secret_file: Callable[[], Callable[[str], str]]
    get_parse_reservation_datetime: Callable[[], Callable[[Any], Optional[datetime]]]
    get_as_utc_datetime: Callable[[], Callable[[Any], Optional[datetime]]]
    get_http_get: Callable[[], Callable[..., Any]]
    get_sql_text: Callable[[], Callable[[str], Any]]
    get_bindparam: Callable[[], Callable[..., Any]]
    get_dispatch_start: Callable[[], Callable[..., Any]]
    get_dispatch_end: Callable[[], Callable[..., Any]]
    get_resolve_host_by_lab: Callable[[], Callable[[str], Optional[Any]]]
    get_record_operation: Callable[[], Callable[..., Any]]
    get_logger: Callable[[], Any]
    get_now: Callable[[], Callable[[], datetime]]


__all__ = ["ReservationRuntimeContext"]
