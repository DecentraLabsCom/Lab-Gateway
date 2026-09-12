"""WinRM session construction with explicit trust and client dependencies."""

from collections.abc import Callable
from typing import Any, Dict, Optional, Tuple


def create_winrm_session(
    host: Dict[str, Any],
    user: str,
    password: str,
    transport: str,
    effective_port: int,
    *,
    read_timeout_sec: Optional[int] = None,
    operation_timeout_sec: Optional[int] = None,
    load_trust: Callable[[Dict[str, Any]], Tuple[str, Dict[str, Any]]],
    session_factory: Callable[..., Any],
) -> Any:
    """Create a validated HTTPS WinRM session using managed host trust."""
    certificate_path, _ = load_trust(host)
    endpoint = f"https://{host.get('address')}:{effective_port}/wsman"
    kwargs: Dict[str, Any] = {
        "auth": (user, password),
        "transport": transport,
        "ca_trust_path": certificate_path,
        "server_cert_validation": "validate",
    }
    if read_timeout_sec is not None:
        kwargs["read_timeout_sec"] = read_timeout_sec
    if operation_timeout_sec is not None:
        kwargs["operation_timeout_sec"] = operation_timeout_sec
    return session_factory(endpoint, **kwargs)
