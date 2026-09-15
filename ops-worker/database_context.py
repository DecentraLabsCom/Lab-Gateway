"""Explicit dependencies for Ops Worker database health checks."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class DatabaseContext:
    """Database health implementation and its SQL/logging ports."""

    database_is_usable: Callable[..., bool]
    get_sql_text: Callable[[], Callable[[str], Any]]
    get_logger: Callable[[], Any]


__all__ = ["DatabaseContext"]
