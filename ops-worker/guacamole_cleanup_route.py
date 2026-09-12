"""Composition for the internal Guacamole temporary-user cleanup route."""

from typing import Any, Callable, Optional, Tuple


def handle_guacamole_cleanup(
    session_id: str,
    *,
    authorize: Callable[[], Optional[Tuple[Any, int]]],
    delete_temporary_user: Callable[[str], bool],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[[str, BaseException], Any],
) -> Any:
    """Delete a temporary user while preserving the internal API contract."""
    auth_response = authorize()
    if auth_response:
        return auth_response
    try:
        deleted = delete_temporary_user(session_id)
        return jsonify({"success": True, "deleted": deleted, "sessionId": session_id})
    except ValueError:
        return jsonify({"success": False, "error": "Invalid Guacamole cleanup request"}), 400
    except Exception as exc:
        return internal_error_response("Guacamole temporary-user cleanup failed", exc, success=False)


__all__ = ["handle_guacamole_cleanup"]
