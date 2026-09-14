"""Composition adapter for Wake-on-LAN orchestration."""

from collections.abc import Mapping
from typing import Any, Optional, Tuple


class WolRuntime:
    """Resolve Wake-on-LAN dependencies from a live worker namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def wol_and_wait(
        self,
        mac: str,
        broadcast: Optional[str],
        port: int,
        ping_target: str,
        attempts: int,
        wait_seconds: float,
        probe_port: Optional[int] = None,
    ) -> Tuple[bool, int]:
        get = self._get
        return get("_wol_and_wait_impl")(
            mac,
            broadcast,
            port,
            ping_target,
            attempts,
            wait_seconds,
            probe_port=probe_port,
            send_magic_packet=get("send_magic_packet"),
            sleep=get("time").sleep,
            host_is_up=get("host_is_up"),
        )


def create_wol_runtime(providers: Mapping[str, Any]) -> WolRuntime:
    """Create a WOL adapter bound to live providers."""
    return WolRuntime(providers)


__all__ = ["WolRuntime", "create_wol_runtime"]
