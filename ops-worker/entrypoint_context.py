"""Explicit dependencies for Ops Worker process startup."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EntrypointContext:
    """Launcher, logging, application and process configuration providers."""

    get_configure_logging_impl: Callable[[], Callable[..., Any]]
    get_log_level: Callable[[], str]
    get_basic_config: Callable[..., Any]
    get_run_impl: Callable[[], Callable[..., Any]]
    get_configure_logging: Callable[[], Callable[..., Any]]
    get_refresh_trust_store: Callable[[], Callable[[Sequence[dict[str, Any]]], Any]]
    get_hosts: Callable[[], Sequence[dict[str, Any]]]
    get_start_scheduler: Callable[[], Callable[..., Any]]
    get_bind: Callable[[], str]
    get_port: Callable[[], int]
    get_serve: Callable[[], Callable[..., Any]]
    get_app: Callable[[], Any]


__all__ = ["EntrypointContext"]
