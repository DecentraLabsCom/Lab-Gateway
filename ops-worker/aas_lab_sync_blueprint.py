"""Flask transport boundary for per-lab AAS synchronization."""

from typing import Any, Callable, Dict, Optional

from flask import Blueprint, jsonify, request

from aas_lab_sync_route import handle_aas_lab_sync


def create_aas_lab_sync_blueprint(
    *,
    find_host_by_lab: Callable[[str], Optional[Dict[str, Any]]],
    parse_bool: Callable[[Any, bool], bool],
    poll_heartbeat: Callable[..., Dict[str, Any]],
    load_persisted_heartbeat: Optional[
        Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]
    ],
    sync_lab: Callable[
        [str, Dict[str, Any], Optional[Dict[str, Any]], Dict[str, Any]],
        Dict[str, Any],
    ],
    log_warning: Callable[..., Any],
) -> Blueprint:
    """Create the per-lab AAS sync Blueprint with explicit providers."""
    blueprint = Blueprint("aas_lab_sync", __name__)

    @blueprint.post("/aas-admin/lab/<lab_id>/sync")
    def api_aas_sync_lab(lab_id: str):
        payload: Any = request.get_json(silent=True) or {}
        return handle_aas_lab_sync(
            lab_id,
            payload,
            find_host_by_lab=find_host_by_lab,
            parse_bool=parse_bool,
            poll_heartbeat=poll_heartbeat,
            load_persisted_heartbeat=load_persisted_heartbeat,
            sync_lab=sync_lab,
            log_warning=log_warning,
            jsonify=jsonify,
        )

    return blueprint


__all__ = ["create_aas_lab_sync_blueprint"]
