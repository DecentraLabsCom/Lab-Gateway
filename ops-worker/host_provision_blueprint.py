"""Flask transport boundary for dynamic host provisioning."""

from typing import Any, Callable, Collection, Dict, Optional, Tuple

from flask import Blueprint, jsonify, request

from host_provision_route import handle_host_provision


def create_host_provision_blueprint(
    *,
    resolve_connection: Callable[[Any], Optional[Dict[str, Any]]],
    discover_candidate: Callable[[Dict[str, Any]], Dict[str, Any]],
    enough_discovery_signals: Collection[Any],
    build_host: Callable[
        [Dict[str, Any], Dict[str, Any]], Tuple[Optional[Dict[str, Any]], Optional[str]]
    ],
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    upsert_host: Callable[[Dict[str, Any]], None],
    reload_hosts: Callable[[], Tuple[int, Optional[str]]],
    safe_host_inventory_entry: Callable[..., Dict[str, Any]],
    internal_error_response: Callable[..., Any],
) -> Blueprint:
    """Create the dynamic host provisioning Blueprint with explicit providers."""
    blueprint = Blueprint("host_provision", __name__)

    @blueprint.post("/api/hosts/provision")
    def api_hosts_provision():
        payload: Any = request.get_json(force=True, silent=True) or {}
        return handle_host_provision(
            payload,
            resolve_connection=resolve_connection,
            discover_candidate=discover_candidate,
            enough_discovery_signals=enough_discovery_signals,
            build_host=build_host,
            find_host=find_host,
            upsert_host=upsert_host,
            reload_hosts=reload_hosts,
            safe_host_inventory_entry=safe_host_inventory_entry,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_host_provision_blueprint"]
