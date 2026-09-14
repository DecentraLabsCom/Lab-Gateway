"""Flask transport boundary for the WinRM trust certificate preview route."""

from typing import Any, Callable, Dict, Optional, Type

from flask import Blueprint, jsonify

from winrm_trust_preview_route import handle_winrm_trust_preview


def create_winrm_trust_preview_blueprint(
    *,
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    read_certificate_upload: Callable[[], bytes],
    parse_certificate: Callable[[bytes], Any],
    response_metadata: Callable[[Any, Dict[str, Any], str], Dict[str, Any]],
    validate_certificate: Callable[[Any, Dict[str, Any]], Any],
    request_id: Callable[[], str],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    trust_http_status: Callable[[str], int],
    internal_error_response: Callable[..., Any],
) -> Blueprint:
    """Create the WinRM trust preview Blueprint with explicit providers."""
    blueprint = Blueprint("winrm_trust_preview", __name__)

    @blueprint.post("/api/hosts/<host_name>/winrm-trust/preview")
    def api_preview_winrm_trust(host_name: str):
        return handle_winrm_trust_preview(
            host_name,
            find_host=find_host,
            read_certificate_upload=read_certificate_upload,
            parse_certificate=parse_certificate,
            response_metadata=response_metadata,
            validate_certificate=validate_certificate,
            request_id=request_id,
            trust_error_type=trust_error_type,
            trust_error_payload=trust_error_payload,
            trust_http_status=trust_http_status,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_winrm_trust_preview_blueprint"]
