"""Composition adapter for database health checks."""

from typing import Any

from database_context import DatabaseContext


class DatabaseRuntime:
    """Expose database health checks through explicit dependency ports."""

    def __init__(self, context: DatabaseContext):
        self._context = context

    def database_is_usable(self, engine: Any, statement: str) -> bool:
        return self._context.database_is_usable(
            engine,
            statement,
            sql_text=self._context.get_sql_text(),
            logger=self._context.get_logger(),
        )


def create_database_runtime(context: DatabaseContext) -> DatabaseRuntime:
    """Create a database health adapter bound to explicit ports."""
    return DatabaseRuntime(context)


__all__ = ["DatabaseRuntime", "create_database_runtime"]
