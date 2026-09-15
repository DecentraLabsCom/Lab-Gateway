"""Explicit dependencies for Ops Worker compatibility helpers."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, MutableMapping


@dataclass(frozen=True)
class WorkerCompatibilityContext:
    """Ports for deployment mode, clock and host-registry compatibility behavior."""

    get_is_lite_gateway_impl: Callable[[], Callable[[Mapping[str, str]], bool]]
    get_environ: Callable[[], Mapping[str, str]]
    get_datetime: Callable[[], Any]
    get_timezone: Callable[[], Any]
    get_hosts: Callable[[], Any]
    get_jsonify: Callable[[], Callable[[Mapping[str, Any]], Any]]
    get_hosts_lock: Callable[[], Any]
    get_replace_host_registry_impl: Callable[[], Callable[..., Any]]
    get_reservation_automator: Callable[[], Any]
    set_host_registry: Callable[[MutableMapping[str, Any]], None]


__all__ = ["WorkerCompatibilityContext"]
