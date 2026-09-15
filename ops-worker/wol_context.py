"""Explicit dependencies for Wake-on-LAN orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Tuple


@dataclass(frozen=True)
class WolContext:
    """Wake-on-LAN implementation and network/runtime ports."""

    wol_and_wait: Callable[..., Tuple[bool, int]]
    get_send_magic_packet: Callable[[], Callable[..., Any]]
    get_sleep: Callable[[], Callable[[float], Any]]
    get_host_is_up: Callable[[], Callable[..., bool]]


__all__ = ["WolContext"]
