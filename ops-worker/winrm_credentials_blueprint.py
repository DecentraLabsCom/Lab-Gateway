"""Flask transport boundary for the WinRM credentials route."""

from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from flask import Blueprint, jsonify, request

from winrm_credentials_route import handle_winrm_credentials


def create_winrm_credentials_blueprint(
    *,
    save_credentials: Callable[[str, str, str], None],
    reload_hosts: Callable[[], Tuple[int, Optional[str]]],
    normalize_credential_ref: Callable[[Any], str],
    internal_error_response: Callable[..., Any],
) -> Blueprint:
    """Create the WinRM credentials Blueprint with explicit providers."""
    blueprint = Blueprint("winrm_credentials", __name__)

    @blueprint.post("/api/hosts/winrm-credentials")
    def api_save_winrm_credentials():
        payload: Mapping[str, Any] = request.get_json(force=True, silent=True) or {}
        return handle_winrm_credentials(
            payload,
            save_credentials=save_credentials,
            reload_hosts=reload_hosts,
            normalize_credential_ref=normalize_credential_ref,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_winrm_credentials_blueprint"]
