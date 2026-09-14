"""Flask transport boundary for the host discovery route."""

from typing import Any, Callable, Dict, Mapping, Optional

from flask import Blueprint, jsonify, request

from hosts_discover_route import handle_hosts_discover


def create_hosts_discover_blueprint(
    *,
    resolve_connection: Callable[[Any], Optional[Dict[str, Any]]],
    discover_candidate: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Blueprint:
    """Create the host discovery Blueprint with explicit providers."""
    blueprint = Blueprint("hosts_discover", __name__)

    @blueprint.post("/api/hosts/discover")
    def api_hosts_discover():
        payload: Mapping[str, Any] = request.get_json(force=True, silent=True) or {}
        return handle_hosts_discover(
            payload,
            resolve_connection=resolve_connection,
            discover_candidate=discover_candidate,
            jsonify=jsonify,
        )

    return blueprint


__all__ = ["create_hosts_discover_blueprint"]
