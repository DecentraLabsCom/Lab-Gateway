"""Composition for the public host inventory HTTP route."""

from typing import Any, Callable, Dict


def handle_hosts_inventory(
    *,
    build_inventory: Callable[[], Dict[str, Any]],
    jsonify: Callable[[Any], Any],
) -> Any:
    """Return the current public host inventory response."""
    return jsonify(build_inventory())


__all__ = ["handle_hosts_inventory"]
