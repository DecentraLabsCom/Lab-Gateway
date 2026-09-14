"""Flask transport boundary for the internal Guacamole connection catalog."""

from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify

from guacamole_connection_route import handle_guacamole_connections


def create_guacamole_connections_blueprint(
    *,
    authorize: Callable[[], Any],
    load_connections: Callable[[], Tuple[List[Dict[str, Any]], Optional[str]]],
    safe_connection_response: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Blueprint:
    """Create the Guacamole connection catalog Blueprint with explicit providers."""
    blueprint = Blueprint("guacamole_connections", __name__)

    @blueprint.get("/internal/guacamole/connections")
    def api_internal_guacamole_connections():
        return handle_guacamole_connections(
            authorize=authorize,
            load_connections=load_connections,
            safe_connection_response=safe_connection_response,
            jsonify=jsonify,
        )

    return blueprint


__all__ = ["create_guacamole_connections_blueprint"]
