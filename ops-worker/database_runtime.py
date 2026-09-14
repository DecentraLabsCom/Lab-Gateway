"""Composition adapter for database health checks."""

from collections.abc import Mapping
from typing import Any


class DatabaseRuntime:
    """Resolve database health checks from a live worker provider namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def database_is_usable(self, engine: Any, statement: str) -> bool:
        get = self._get
        return get("_database_is_usable_impl")(
            engine,
            statement,
            sql_text=get("text"),
            logger=get("logging"),
        )


def create_database_runtime(providers: Mapping[str, Any]) -> DatabaseRuntime:
    """Create a database health adapter bound to live providers."""
    return DatabaseRuntime(providers)


__all__ = ["DatabaseRuntime", "create_database_runtime"]
