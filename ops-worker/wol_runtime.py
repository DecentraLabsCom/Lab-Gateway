"""Composition adapter for Wake-on-LAN orchestration."""

from typing import Any, Optional, Tuple

from wol_context import WolContext


class WolRuntime:
    """Expose Wake-on-LAN orchestration through explicit dependency ports."""

    def __init__(self, context: WolContext):
        self._context = context

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
        return self._context.wol_and_wait(
            mac,
            broadcast,
            port,
            ping_target,
            attempts,
            wait_seconds,
            probe_port=probe_port,
            send_magic_packet=self._context.get_send_magic_packet(),
            sleep=self._context.get_sleep(),
            host_is_up=self._context.get_host_is_up(),
        )


def create_wol_runtime(context: WolContext) -> WolRuntime:
    """Create a WOL adapter bound to explicit ports."""
    return WolRuntime(context)


__all__ = ["WolRuntime", "create_wol_runtime"]
