"""Flask transport boundary for the host catalog reload route."""

from typing import Any, Callable, Optional, Tuple

from flask import Blueprint, jsonify

from hosts_reload_route import handle_hosts_reload


def create_hosts_reload_blueprint(
    *,
    reload_hosts: Callable[[], Tuple[int, Optional[str]]],
) -> Blueprint:
    """Create the host catalog reload Blueprint with an explicit provider."""
    blueprint = Blueprint("hosts_reload", __name__)

    @blueprint.post("/api/hosts/reload")
    def api_hosts_reload():
        return handle_hosts_reload(
            reload_hosts=reload_hosts,
            jsonify=jsonify,
        )

    return blueprint


__all__ = ["create_hosts_reload_blueprint"]
