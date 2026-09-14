"""Composition for the internal Guacamole temporary-user provision route."""

from collections.abc import Mapping
from typing import Any, Callable, Dict, Optional, Tuple


def check_guacamole_provisioner_auth(
    headers: Mapping[str, Any],
    *,
    expected_token: str,
    token_header: str,
    jsonify: Callable[[Any], Any],
) -> Any:
    """Validate the gateway-local Guacamole provisioner credential."""
    expected = str(expected_token or "").strip()
    if not expected:
        return None
    provided = headers.get(token_header)
    if not provided and token_header.lower() != "x-lab-manager-token":
        provided = headers.get("X-Lab-Manager-Token")
    if provided != expected:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return None


def handle_guacamole_provision(
    payload: Mapping[str, Any],
    *,
    authorize: Callable[[], Optional[Tuple[Any, int]]],
    provision_temporary_user: Callable[[str, str, Any, bool], Dict[str, Any]],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[..., Any],
) -> Any:
    """Provision a temporary Guacamole user while preserving its API contract."""
    auth_response = authorize()
    if auth_response:
        return auth_response

    try:
        activate = payload.get("activate", True)
        if not isinstance(activate, bool):
            raise ValueError("activate must be a boolean")
        result = provision_temporary_user(
            str(payload.get("selector") or "").strip(),
            str(payload.get("sessionId") or "").strip(),
            payload.get("validUntilEpochSeconds"),
            activate,
        )
        return jsonify(result)
    except ValueError as exc:
        error = (
            "activate must be a boolean"
            if str(exc) == "activate must be a boolean"
            else "Invalid Guacamole provisioning request"
        )
        return jsonify({"success": False, "error": error}), 400
    except Exception as exc:
        return internal_error_response("Guacamole provisioning failed", exc, success=False)


__all__ = ["handle_guacamole_provision"]
