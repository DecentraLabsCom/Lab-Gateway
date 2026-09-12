"""Composition for the WinRM trust status HTTP route."""

from typing import Any, Callable, Dict, Optional, Type


def handle_winrm_trust_get(
    host_name: str,
    *,
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    inspect_trust: Callable[[Dict[str, Any]], Dict[str, Any]],
    request_id: Callable[[], str],
    trust_error_type: Type[BaseException],
    trust_error_payload: Callable[[Any, str], Dict[str, Any]],
    trust_http_status: Callable[[str], int],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[[str, BaseException], Any],
) -> Any:
    """Return the current host trust status while preserving public errors."""
    host = find_host(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404

    try:
        trust = inspect_trust(host)
        return jsonify({
            "requestId": request_id(),
            "host": host.get("name"),
            "address": host.get("address"),
            "trust": trust,
        })
    except (ValueError, trust_error_type) as exc:
        code = getattr(exc, "code", "WINRM_TRUST_INVALID")
        return jsonify(trust_error_payload(host_name, code)), trust_http_status(code)
    except Exception as exc:
        return internal_error_response("WinRM trust status failed", exc)


__all__ = ["handle_winrm_trust_get"]
