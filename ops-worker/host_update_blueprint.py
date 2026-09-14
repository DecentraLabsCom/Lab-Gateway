"""Flask transport boundary for dynamic host updates."""

from typing import Any, Callable, Dict, Optional, Tuple

from flask import Blueprint, jsonify, request

from host_update_route import handle_host_update


def create_host_update_blueprint(
    *,
    update_host: Callable[
        [str, Dict[str, Any]], Tuple[Optional[Dict[str, Any]], Optional[str]]
    ],
    reload_hosts: Callable[[], Tuple[int, Optional[str]]],
    safe_host_inventory_entry: Callable[..., Dict[str, Any]],
    internal_error_response: Callable[..., Any],
) -> Blueprint:
    """Create the dynamic host update Blueprint with explicit providers."""
    blueprint = Blueprint("host_update", __name__)

    @blueprint.patch("/api/hosts/<host_name>")
    def api_hosts_update(host_name: str):
        payload: Any = request.get_json(force=True, silent=True) or {}
        return handle_host_update(
            host_name,
            payload,
            update_host=update_host,
            reload_hosts=reload_hosts,
            safe_host_inventory_entry=safe_host_inventory_entry,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_host_update_blueprint"]
