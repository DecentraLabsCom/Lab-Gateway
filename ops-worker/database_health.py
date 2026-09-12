"""Database health checks with explicit engine and logging dependencies."""

from collections.abc import Callable
from typing import Any, Optional


def database_is_usable(
    engine: Optional[Any],
    statement: str,
    *,
    sql_text: Callable[[str], Any],
    logger: Any,
) -> bool:
    """Execute a health-check statement and fail closed on database errors."""
    if not engine:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(sql_text(statement)).first()
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Health database check failed: %s", exc)
        return False
