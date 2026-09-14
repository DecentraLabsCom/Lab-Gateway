"""Flask transport boundary for the heartbeat polling route."""

from typing import Any, Callable, Dict, Mapping, Optional, Type

from flask import Blueprint, jsonify, request

from heartbeat_route import handle_heartbeat_poll


def create_heartbeat_poll_blueprint(
    *,
    find_host: Callable[[Any], Optional[Dict[str, Any]]],
    poll_heartbeat: Callable[[Dict[str, Any], bool], Dict[str, Any]],
    now: Callable[[], float],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    missing_credentials_predicate: Callable[[ValueError], bool],
    credentials_required_message: Callable[[], str],
    internal_error_response: Callable[[str, BaseException], Any],
) -> Blueprint:
    """Create the heartbeat polling Blueprint with explicit providers."""
    blueprint = Blueprint("heartbeat_poll", __name__)

    @blueprint.post("/api/heartbeat/poll")
    def api_poll_heartbeat():
        payload: Mapping[str, Any] = request.get_json(force=True, silent=True) or {}
        return handle_heartbeat_poll(
            payload,
            find_host=find_host,
            poll_heartbeat=poll_heartbeat,
            now=now,
            jsonify=jsonify,
            trust_error_type=trust_error_type,
            trust_error_payload=trust_error_payload,
            missing_credentials_predicate=missing_credentials_predicate,
            credentials_required_message=credentials_required_message(),
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_heartbeat_poll_blueprint"]
