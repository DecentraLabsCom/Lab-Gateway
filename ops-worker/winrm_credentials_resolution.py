"""Resolution of stored WinRM credentials with explicit dependencies."""

from collections.abc import Callable
from typing import Any, Dict, Optional, Tuple


def normalize_credential_ref(value: Any) -> str:
    """Normalize a stored credential reference for case-insensitive lookup."""
    return str(value or "").strip().lower()


def credential_ref_for_host(
    host: Dict[str, Any],
    *,
    normalize_ref: Callable[[Any], str] = normalize_credential_ref,
) -> str:
    """Select the stable credential reference configured for one host."""
    return normalize_ref(
        host.get("credential_ref") or host.get("address") or host.get("name")
    )


def resolve_winrm_credentials(
    host: Dict[str, Any],
    user: Optional[str],
    password: Optional[str],
    *,
    credential_ref_for_host: Callable[[Dict[str, Any]], str],
    load_credentials: Callable[[str], Optional[Dict[str, str]]],
    required_message: str,
) -> Tuple[str, str]:
    """Resolve credentials from the encrypted store, never from request data."""
    if user or password:
        raise ValueError("WinRM credentials must be stored through the credentials endpoint")
    credentials = load_credentials(credential_ref_for_host(host))
    if not credentials:
        raise ValueError(required_message)
    return credentials["user"], credentials["password"]
