"""Flask transport boundary for Wake-on-LAN and WinRM routes."""

from collections.abc import Mapping
from typing import Any, Callable, Collection, Dict, Optional, Type

from flask import Blueprint, jsonify, request

from wol_defaults import DEFAULT_WOL_PING_TIMEOUT_SECONDS
from station_wake import wait_for_station_identity
from winrm_route import handle_winrm
from wol_route import handle_wol


def create_physical_operations_blueprint(
    *,
    find_host: Callable[[Any], Optional[Dict[str, Any]]],
    is_valid_ping_target: Callable[[str], bool],
    wol_and_wait: Callable[..., Any],
    now: Callable[[], float],
    allowed_commands: Collection[str],
    run_command: Callable[..., Dict[str, Any]],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    internal_error_response: Callable[..., Any],
    probe_station: Optional[Callable[[Mapping[str, Any]], Dict[str, Any]]] = None,
) -> Blueprint:
    """Create the physical-operations Blueprint with explicit providers."""
    blueprint = Blueprint("physical_operations", __name__)

    @blueprint.post("/api/wol")
    def api_wol():
        payload: Any = request.get_json(force=True, silent=True) or {}
        return handle_wol(
            payload,
            find_host=find_host,
            is_valid_ping_target=is_valid_ping_target,
            wol_and_wait=wol_and_wait,
            now=now,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
            verify_station=(
                (lambda host: _station_identity_verified(host, probe_station))
                if probe_station is not None
                else None
            ),
        )

    @blueprint.post("/api/winrm")
    def api_winrm():
        payload: Any = request.get_json(force=True, silent=True) or {}
        return handle_winrm(
            payload,
            allowed_commands=allowed_commands,
            find_host=find_host,
            run_command=run_command,
            trust_error_type=trust_error_type,
            trust_error_payload=trust_error_payload,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


def _station_identity_verified(
    host: Mapping[str, Any],
    probe_station: Optional[Callable[[Mapping[str, Any]], Dict[str, Any]]],
) -> bool:
    if probe_station is None:
        return False
    return wait_for_station_identity(
        host,
        probe_station,
        DEFAULT_WOL_PING_TIMEOUT_SECONDS,
    )


__all__ = ["create_physical_operations_blueprint"]
