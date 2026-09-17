"""Wake-on-LAN retry orchestration."""

from typing import Any, Callable, Optional, Tuple


def wol_and_wait(
    mac: str,
    broadcast: Optional[str],
    port: int,
    ping_target: str,
    attempts: int,
    wait_seconds: float,
    probe_port: Optional[int] = None,
    *,
    send_magic_packet: Callable[..., Any],
    sleep: Callable[[float], Any],
    host_is_up: Callable[..., bool],
) -> Tuple[bool, int]:
    """Send WoL packets and stop after the first successful reachability probe."""
    for attempt in range(1, attempts + 1):
        send_magic_packet(
            mac,
            host=broadcast or "255.255.255.255",
            port=port,
        )
        sleep(wait_seconds)
        if host_is_up(ping_target, wait_seconds, probe_port=probe_port):
            return True, attempt
    return False, attempts


__all__ = ["wol_and_wait"]
