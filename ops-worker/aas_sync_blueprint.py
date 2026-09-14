"""Flask transport boundary for the Lab Manager AAS sync route."""

from typing import Any, Callable, Dict, Mapping, Optional

from flask import Blueprint, jsonify, request

from aas_sync_route import handle_aas_sync


def create_aas_sync_blueprint(
    *,
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    sync_lab: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    log_failure: Callable[..., Any],
) -> Blueprint:
    """Create the AAS sync Blueprint with explicit providers."""
    blueprint = Blueprint("aas_sync", __name__)

    @blueprint.post("/api/aas-sync")
    def api_aas_sync():
        payload: Mapping[str, Any] = request.get_json(force=True, silent=True) or {}
        return handle_aas_sync(
            payload,
            find_host=find_host,
            sync_lab=sync_lab,
            log_failure=log_failure,
            jsonify=jsonify,
        )

    return blueprint


__all__ = ["create_aas_sync_blueprint"]
