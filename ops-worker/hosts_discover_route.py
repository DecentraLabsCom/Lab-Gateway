"""Composition for the host discovery HTTP route."""

from typing import Any, Callable, Dict, Mapping, Optional


def handle_hosts_discover(
    payload: Mapping[str, Any],
    *,
    resolve_connection: Callable[[Any], Optional[Dict[str, Any]]],
    discover_candidate: Callable[[Dict[str, Any]], Dict[str, Any]],
    jsonify: Callable[[Any], Any],
) -> Any:
    """Resolve a Guacamole connection and return its discovery projection."""
    connection_id = payload.get("connectionId") or payload.get("connection_id")
    if connection_id in (None, ""):
        return jsonify({"error": "connectionId is required"}), 400

    connection = resolve_connection(connection_id)
    if not connection:
        return jsonify({"error": f"Guacamole connection {connection_id} not found"}), 404

    return jsonify(discover_candidate(connection))


__all__ = ["handle_hosts_discover"]
