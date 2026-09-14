"""Flask transport boundary for the WinRM trust status route."""

from typing import Any, Callable, Dict, Optional, Type

from flask import Blueprint, jsonify

from winrm_trust_route import handle_winrm_trust_get


def create_winrm_trust_blueprint(
    *,
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    inspect_trust: Callable[[Dict[str, Any]], Dict[str, Any]],
    request_id: Callable[[], str],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    trust_http_status: Callable[[str], int],
    internal_error_response: Callable[[str, BaseException], Any],
) -> Blueprint:
    """Create the WinRM trust Blueprint with explicit runtime providers."""
    blueprint = Blueprint("winrm_trust", __name__)

    @blueprint.get("/api/hosts/<host_name>/winrm-trust")
    def api_get_winrm_trust(host_name: str):
        return handle_winrm_trust_get(
            host_name,
            find_host=find_host,
            inspect_trust=inspect_trust,
            request_id=request_id,
            trust_error_type=trust_error_type,
            trust_error_payload=trust_error_payload,
            trust_http_status=trust_http_status,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_winrm_trust_blueprint"]
