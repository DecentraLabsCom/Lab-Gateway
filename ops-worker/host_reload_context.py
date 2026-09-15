"""Explicit dependencies for host catalog reload orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class HostReloadContext:
    """Dependencies required to load and atomically publish host state."""

    reload_hosts: Callable[..., Tuple[int, Optional[str]]]
    load_config: Callable[[], Dict[str, Any]]
    registry_factory: Callable[[Dict[str, Any]], Any]
    refresh_trust_store: Callable[[Any], Any]
    replace_registry: Callable[[Any], None]
    get_logger: Callable[[], Any]


__all__ = ["HostReloadContext"]
