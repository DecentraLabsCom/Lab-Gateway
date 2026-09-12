"""Heartbeat polling coordination with explicit registry and logger dependencies."""

from collections.abc import Callable
from typing import Any


def poll_all_hosts(
    registry: Any,
    poll_heartbeat: Callable[..., Any],
    logger: Any,
) -> None:
    """Poll every registered host while allowing individual failures."""
    for host in registry.all_hosts():
        try:
            poll_heartbeat(host, include_events=True)
            logger.info("Polled heartbeat for %s", host.get("name"))
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Heartbeat poll failed for %s: %s", host.get("name"), exc)
