"""Flask transport boundary for the public host inventory route."""

from typing import Any, Callable, Dict

from flask import Blueprint, jsonify

from hosts_route import handle_hosts_inventory


def create_hosts_blueprint(
    *,
    build_inventory: Callable[[], Dict[str, Any]],
) -> Blueprint:
    """Create the host inventory Blueprint with an explicit runtime provider."""
    blueprint = Blueprint("hosts", __name__)

    @blueprint.get("/api/hosts")
    def api_hosts_inventory():
        return handle_hosts_inventory(
            build_inventory=build_inventory,
            jsonify=jsonify,
        )

    return blueprint


__all__ = ["create_hosts_blueprint"]
