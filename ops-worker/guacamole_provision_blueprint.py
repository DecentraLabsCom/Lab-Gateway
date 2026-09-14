"""Flask transport boundary for the internal Guacamole user resource."""

from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from flask import Blueprint, jsonify, request

from guacamole_cleanup_route import handle_guacamole_cleanup
from guacamole_provision_route import handle_guacamole_provision


def create_guacamole_provision_blueprint(
    *,
    authorize: Callable[[], Optional[Tuple[Any, int]]],
    provision_temporary_user: Callable[[str, str, Any, bool], Dict[str, Any]],
    delete_temporary_user: Callable[[str], bool],
    internal_error_response: Callable[..., Any],
) -> Blueprint:
    """Create the Guacamole temporary-user Blueprint with explicit providers."""
    blueprint = Blueprint("guacamole_provision", __name__)

    @blueprint.post("/internal/guacamole/provision")
    def api_internal_guacamole_provision():
        payload: Mapping[str, Any] = request.get_json(silent=True) or {}
        return handle_guacamole_provision(
            payload,
            authorize=authorize,
            provision_temporary_user=provision_temporary_user,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    @blueprint.delete("/internal/guacamole/provision/<session_id>")
    def api_internal_guacamole_delete(session_id: str):
        return handle_guacamole_cleanup(
            session_id,
            authorize=authorize,
            delete_temporary_user=delete_temporary_user,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_guacamole_provision_blueprint"]
