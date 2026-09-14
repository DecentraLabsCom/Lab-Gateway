"""Flask transport boundary for WinRM trust mutation routes."""

from typing import Any, Callable, Dict, Optional, Type

from flask import Blueprint, jsonify, request
from werkzeug.datastructures import Headers

from winrm_trust_mutation_route import handle_winrm_trust_delete, handle_winrm_trust_put


def create_winrm_trust_mutation_blueprint(
    *,
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    request_value: Callable[[str], str],
    normalize_trust_ref: Callable[[str], str],
    trust_ref_for_host: Callable[[Dict[str, Any]], str],
    read_certificate_upload: Callable[[], bytes],
    parse_certificate: Callable[[bytes], Any],
    validate_certificate: Callable[[Any, Dict[str, Any]], Dict[str, Any]],
    store_trust: Callable[[Dict[str, Any], Any], Dict[str, Any]],
    delete_trust: Callable[[Dict[str, Any]], None],
    inspect_trust: Callable[[Dict[str, Any]], Dict[str, Any]],
    request_id: Callable[[], str],
    sanitize_log_value: Callable[[Any], str],
    log_info: Callable[..., Any],
    log_warning: Callable[..., Any],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    trust_http_status: Callable[[str], int],
    fingerprint_confirmation_required_message: str,
    fingerprint_mismatch_message: str,
    trust_ref_mismatch_message: str,
    internal_error_response: Callable[..., Any],
) -> Blueprint:
    """Create the WinRM trust mutation Blueprint with explicit providers."""
    blueprint = Blueprint("winrm_trust_mutation", __name__)

    @blueprint.put("/api/hosts/<host_name>/winrm-trust")
    def api_save_winrm_trust(host_name: str):
        headers: Headers = request.headers
        return handle_winrm_trust_put(
            host_name,
            headers=headers,
            find_host=find_host,
            request_value=request_value,
            normalize_trust_ref=normalize_trust_ref,
            trust_ref_for_host=trust_ref_for_host,
            read_certificate_upload=read_certificate_upload,
            parse_certificate=parse_certificate,
            validate_certificate=validate_certificate,
            store_trust=store_trust,
            request_id=request_id,
            sanitize_log_value=sanitize_log_value,
            log_info=log_info,
            log_warning=log_warning,
            trust_error_type=trust_error_type,
            trust_error_payload=trust_error_payload,
            trust_http_status=trust_http_status,
            fingerprint_confirmation_required_message=fingerprint_confirmation_required_message,
            fingerprint_mismatch_message=fingerprint_mismatch_message,
            trust_ref_mismatch_message=trust_ref_mismatch_message,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    @blueprint.delete("/api/hosts/<host_name>/winrm-trust")
    def api_delete_winrm_trust(host_name: str):
        return handle_winrm_trust_delete(
            host_name,
            find_host=find_host,
            delete_trust=delete_trust,
            inspect_trust=inspect_trust,
            request_id=request_id,
            sanitize_log_value=sanitize_log_value,
            log_info=log_info,
            trust_error_type=trust_error_type,
            trust_error_payload=trust_error_payload,
            trust_http_status=trust_http_status,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_winrm_trust_mutation_blueprint"]
