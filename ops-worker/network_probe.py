"""Small network reachability probes used by discovery and WoL."""

from collections.abc import Callable
from typing import Any, Optional


def is_valid_ping_target(target: Any) -> bool:
    """Validate a DNS-style target without a backtracking-prone regex."""
    if not target or len(str(target)) > 253:
        return False
    labels = str(target).rstrip(".").split(".")
    if not labels or any(not label or len(label) > 63 for label in labels):
        return False
    return all(
        label[0].isalnum()
        and label[-1].isalnum()
        and all(char.isalnum() or char == "-" for char in label)
        for label in labels
    )


def host_is_up(
    target: str,
    timeout: float,
    probe_port: Optional[int] = None,
    *,
    is_valid_target: Callable[[str], bool],
    winrm_port: int,
    create_connection: Callable[..., Any],
    warn: Callable[[str], Any],
) -> bool:
    """Probe the canonical WinRM listener without invoking a shell."""
    if not target:
        return False
    target = str(target).strip()
    if not is_valid_target(target):
        warn("Invalid reachability target rejected")
        return False

    if probe_port is None:
        probe_port = winrm_port
    if probe_port != winrm_port:
        warn("Invalid reachability port rejected")
        return False
    try:
        with create_connection((target, probe_port), timeout=max(float(timeout), 0.1)):
            return True
    except (OSError, ValueError, TypeError):
        return False


def tcp_port_open(
    host: str,
    port: int,
    timeout: Optional[float] = None,
    *,
    default_timeout: float,
    create_connection: Callable[..., Any],
) -> bool:
    """Return whether a TCP connection can be opened within the timeout."""
    try:
        with create_connection((host, port), timeout or default_timeout):
            return True
    except OSError:
        return False


__all__ = ["host_is_up", "is_valid_ping_target", "tcp_port_open"]
