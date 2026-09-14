"""Composition of the optional power runtime and its credential stores."""

from dataclasses import dataclass
from typing import Any, Callable, MutableMapping, Optional


@dataclass(frozen=True)
class PowerRuntimeState:
    """Resources published through the worker's historical globals/extensions."""

    operation_store: Optional[Any]
    credential_store: Any
    runtime: Any


def create_power_runtime(
    *,
    extensions: MutableMapping[str, Any],
    db_engine: Optional[Any],
    config_path: str,
    status_cache_ttl_seconds: float,
    operation_store_factory: Callable[[Any], Any],
    credential_store_factory: Callable[[], Any],
    runtime_from_path: Callable[..., Any],
    runtime_from_config: Callable[..., Any],
    record_operation: Callable[..., Any],
    logger: Any,
) -> PowerRuntimeState:
    """Create power resources, failing closed when the catalog is unavailable."""
    operation_store = operation_store_factory(db_engine) if db_engine else None
    credential_store = credential_store_factory()
    extensions["power_credential_store"] = credential_store
    runtime_kwargs = {
        "record_operation": record_operation,
        "operation_store": operation_store,
        "credential_resolver": credential_store.get,
        "status_cache_ttl_seconds": status_cache_ttl_seconds,
    }
    try:
        runtime = runtime_from_path(config_path, **runtime_kwargs)
    except Exception as exc:  # pylint: disable=broad-except
        # A malformed or unavailable power catalog must not prevent unrelated
        # Lab Station operations from starting.
        logger.error("Power configuration unavailable: %s", type(exc).__name__)
        runtime = runtime_from_config(
            {"controllers": [], "outlets": [], "policies": []},
            **runtime_kwargs,
        )
    extensions["power_runtime"] = runtime
    return PowerRuntimeState(
        operation_store=operation_store,
        credential_store=credential_store,
        runtime=runtime,
    )


__all__ = ["PowerRuntimeState", "create_power_runtime"]
