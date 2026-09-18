"""Composition for the local-mode toggle HTTP route."""

from typing import Any, Callable, Dict, Optional

from runtime_values import DEFAULT_LOCAL_MODE_FLAG_PATH


def get_local_mode_flag_path(host: Dict[str, Any]) -> str:
    """Return the configured Lab Station local-mode flag path."""
    return host.get("local_mode_flag_path", DEFAULT_LOCAL_MODE_FLAG_PATH)


def handle_local_mode(
    payload: Dict[str, Any],
    *,
    parse_bool: Callable[[Any, bool], bool],
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    get_flag_path: Callable[[Dict[str, Any]], str],
    write_remote_file: Callable[[Dict[str, Any], str, str, Optional[str], Optional[str], Optional[str], Optional[bool], Optional[int]], None],
    remove_remote_file: Callable[[Dict[str, Any], str, Optional[str], Optional[str], Optional[str], Optional[bool], Optional[int]], None],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[..., Any],
) -> Any:
    """Toggle a host's Lab Station local-mode flag without changing its contract."""
    host_name = payload.get("host")
    if host_name is None:
        return jsonify({"error": "host is required"}), 400
    enabled = payload.get("enabled")
    if enabled is None:
        return jsonify({"error": "enabled is required"}), 400
    enabled = parse_bool(enabled, False)

    host = find_host(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found"}), 404

    flag_path = get_flag_path(host)
    try:
        if enabled:
            write_remote_file(host, flag_path, "1", None, None, None, None, None)
        else:
            remove_remote_file(host, flag_path, None, None, None, None, None)
    except Exception as exc:
        return internal_error_response(f"Local mode toggle failed for {host_name}", exc)

    return jsonify({"host": host_name, "localModeEnabled": enabled}), 200


__all__ = ["handle_local_mode"]
