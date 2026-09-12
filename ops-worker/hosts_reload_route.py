"""Composition for the host catalog reload HTTP route."""

from typing import Any, Callable, Optional, Tuple


def handle_hosts_reload(
    *,
    reload_hosts: Callable[[], Tuple[int, Optional[str]]],
    jsonify: Callable[[Any], Any],
) -> Any:
    """Reload the host catalog and return its stable public response."""
    count, error = reload_hosts()
    if error:
        return jsonify({"error": "Hosts configuration reload failed"}), 500
    return jsonify({"reloaded": True, "hosts": count})


__all__ = ["handle_hosts_reload"]
