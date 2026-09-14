"""Construction of the initial catalog and database runtime state."""

from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class RuntimeState:
    """Immutable snapshot used to publish the worker's historical globals."""

    hosts: Any
    ops_dsn: Optional[str]
    db_engine: Optional[Any]
    guacamole_dsn: Optional[str]
    guacamole_db_engine: Optional[Any]
    hosts_lock: Any


def replace_host_registry(
    registry: Any,
    *,
    set_registry: Callable[[Any], None],
    reservation_automator: Any,
) -> None:
    """Publish a new host registry and keep reservation orchestration aligned."""
    set_registry(registry)
    reservation_automator.registry = registry


def _create_engine_if_configured(
    dsn: Optional[str],
    *,
    create_engine: Callable[..., Any],
) -> Optional[Any]:
    if not dsn:
        return None
    return create_engine(dsn, pool_pre_ping=True)


def create_runtime_state(
    *,
    load_hosts: Callable[[], Any],
    registry_factory: Callable[[Any], Any],
    build_ops_dsn: Callable[[], Optional[str]],
    build_guacamole_dsn: Callable[[], Optional[str]],
    create_engine: Callable[..., Any],
    lock_factory: Callable[[], Any] = RLock,
) -> RuntimeState:
    """Build the catalog and both optional engines in the legacy order."""
    hosts_lock = lock_factory()
    hosts = registry_factory(load_hosts())
    ops_dsn = build_ops_dsn()
    db_engine = _create_engine_if_configured(ops_dsn, create_engine=create_engine)
    guacamole_dsn = build_guacamole_dsn()
    guacamole_db_engine = _create_engine_if_configured(
        guacamole_dsn,
        create_engine=create_engine,
    )
    return RuntimeState(
        hosts=hosts,
        ops_dsn=ops_dsn,
        db_engine=db_engine,
        guacamole_dsn=guacamole_dsn,
        guacamole_db_engine=guacamole_db_engine,
        hosts_lock=hosts_lock,
    )


__all__ = ["RuntimeState", "create_runtime_state", "replace_host_registry"]
