"""Flask transport boundary for the Lab Station local-mode route."""

from typing import Any, Callable, Dict, Optional

from flask import Blueprint, jsonify, request

from local_mode_route import handle_local_mode


def create_local_mode_blueprint(
    *,
    parse_bool: Callable[[Any, bool], bool],
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    get_flag_path: Callable[[Dict[str, Any]], str],
    write_remote_file: Callable[..., None],
    remove_remote_file: Callable[..., None],
    internal_error_response: Callable[..., Any],
) -> Blueprint:
    """Create the local-mode Blueprint with explicit remote-operation providers."""
    blueprint = Blueprint("local_mode", __name__)

    @blueprint.post("/api/hosts/local-mode")
    def api_hosts_local_mode():
        payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
        return handle_local_mode(
            payload,
            parse_bool=parse_bool,
            find_host=find_host,
            get_flag_path=get_flag_path,
            write_remote_file=write_remote_file,
            remove_remote_file=remove_remote_file,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_local_mode_blueprint"]
