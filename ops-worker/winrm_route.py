"""Composition for the WinRM command execution HTTP route."""

from typing import Any, Callable, Collection, Dict, Optional, Type


def handle_winrm(
    payload: Any,
    *,
    allowed_commands: Collection[str],
    find_host: Callable[[Any], Optional[Dict[str, Any]]],
    run_command: Callable[..., Dict[str, Any]],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[[str, BaseException], Any],
) -> Any:
    """Validate a command request and forward execution to the WinRM service."""
    host_name = payload.get("host")
    command = payload.get("command")
    args = payload.get("args") or []
    if not host_name or not command:
        return jsonify({"error": "host and command are required"}), 400
    if command not in allowed_commands:
        return jsonify({"error": f"command '{command}' not allowed"}), 400
    host = find_host(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404
    try:
        result = run_command(
            host=host,
            command=command,
            args=args,
            user=None,
            password=None,
            transport=payload.get("transport"),
            use_ssl=payload.get("use_ssl"),
            port=payload.get("port"),
        )
        return jsonify(result)
    except Exception as exc:
        if isinstance(exc, trust_error_type):
            code = str(getattr(exc, "code", ""))
            return jsonify(trust_error_payload(host_name, code)), 409
        return internal_error_response("WinRM exec failed", exc)


__all__ = ["handle_winrm"]
