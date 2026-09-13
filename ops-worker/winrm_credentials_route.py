"""Composition for the WinRM credentials HTTP route."""

from typing import Any, Callable, Mapping, Optional, Tuple


def handle_winrm_credentials(
    payload: Mapping[str, Any],
    *,
    save_credentials: Callable[[str, str, str], None],
    reload_hosts: Callable[[], Tuple[int, Optional[str]]],
    normalize_credential_ref: Callable[[Any], str],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[..., Any],
) -> Any:
    """Persist credentials and reload hosts without returning secret values."""
    credential_ref = payload.get("credentialRef") or payload.get("credential_ref")
    user = payload.get("user") or payload.get("username")
    password = payload.get("password")
    try:
        save_credentials(
            str(credential_ref or ""),
            str(user or ""),
            str(password or ""),
        )
        count, reload_error = reload_hosts()
    except ValueError:
        return jsonify({"error": "Invalid WinRM credentials request"}), 400
    except Exception as exc:
        return internal_error_response("Failed to save WinRM credentials", exc)
    if reload_error:
        return jsonify({"error": "Hosts configuration reload failed"}), 500
    return jsonify({
        "saved": True,
        "credentialRef": normalize_credential_ref(credential_ref),
        "hosts": count,
    })


__all__ = ["handle_winrm_credentials"]
