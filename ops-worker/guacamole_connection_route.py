"""Composition for the internal Guacamole connection catalog route."""

from typing import Any, Callable, Dict, List, Optional, Tuple


def handle_guacamole_connections(
    *,
    authorize: Callable[[], Any],
    load_connections: Callable[[], Tuple[List[Dict[str, Any]], Optional[str]]],
    safe_connection_response: Callable[[Dict[str, Any]], Dict[str, Any]],
    jsonify: Callable[[Any], Any],
) -> Any:
    """Return the authorized Guacamole connection catalog response."""
    auth_response = authorize()
    if auth_response:
        return auth_response
    connections, error = load_connections()
    if error:
        return jsonify({"success": False, "error": error}), 503
    return jsonify({
        "success": True,
        "connections": [safe_connection_response(connection) for connection in connections],
    })


__all__ = ["handle_guacamole_connections"]
