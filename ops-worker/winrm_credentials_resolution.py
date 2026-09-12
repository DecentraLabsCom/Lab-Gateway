"""Resolution of stored WinRM credentials with explicit dependencies."""

from collections.abc import Callable
from typing import Any, Dict, Optional, Tuple


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
