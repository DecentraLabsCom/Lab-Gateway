"""Explicit dependency ports for the common lab resolver."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LabResolutionContext:
    """Runtime configuration and live catalog dependencies."""

    get_catalog_url: Callable[[], str]
    get_catalog_token: Callable[[], str]
    get_catalog_token_header: Callable[[], str]
    get_catalog_allow_insecure: Callable[[], bool]
    get_catalog_timeout: Callable[[], float]
    get_catalog_cache_seconds: Callable[[], float]
    get_http_get: Callable[[], Callable[..., Any]]
    get_logger: Callable[[], Any]
    get_cache_lock: Callable[[], Any]
    get_host_registry: Callable[[], Any]
    get_guacamole_connections: Callable[[], Any]
    get_parse_selector: Callable[[], Callable[[Any], int]]
    get_normalize_key: Callable[[], Callable[[Any], str]]
    get_monotonic: Callable[[], Callable[[], float]]


__all__ = ["LabResolutionContext"]
