"""Composition boundary for the provider lab-resolution runtime."""

from collections.abc import Callable
from threading import RLock
from typing import Any

from lab_resolution_context import LabResolutionContext
from lab_resolution_runtime import LabResolutionRuntime, create_lab_resolution_runtime
from runtime_config import RuntimePolicy


def create_lab_resolution_composition(
    policy: RuntimePolicy,
    *,
    get_host_registry: Callable[[], Any],
    get_guacamole_connections: Callable[[], Any],
    get_parse_selector: Callable[[], Callable[[Any], int]],
    get_normalize_key: Callable[[], Callable[[Any], str]],
    get_http_get: Callable[[], Callable[..., Any]],
    get_logger: Callable[[], Any],
    get_monotonic: Callable[[], Callable[[], float]],
) -> LabResolutionRuntime:
    """Build the resolver from immutable policy and live worker dependencies."""
    catalog_lock = RLock()
    context = LabResolutionContext(
        get_catalog_url=lambda: policy.lab_catalog_url,
        get_catalog_token=lambda: policy.lab_catalog_token,
        get_catalog_token_header=lambda: policy.lab_catalog_token_header,
        get_catalog_allow_insecure=lambda: policy.lab_catalog_allow_insecure,
        get_catalog_timeout=lambda: policy.lab_catalog_timeout_seconds,
        get_catalog_cache_seconds=lambda: policy.lab_catalog_cache_seconds,
        get_http_get=get_http_get,
        get_logger=get_logger,
        get_cache_lock=lambda: catalog_lock,
        get_host_registry=get_host_registry,
        get_guacamole_connections=get_guacamole_connections,
        get_parse_selector=get_parse_selector,
        get_normalize_key=get_normalize_key,
        get_monotonic=get_monotonic,
    )
    return create_lab_resolution_runtime(context)


__all__ = ["create_lab_resolution_composition"]
