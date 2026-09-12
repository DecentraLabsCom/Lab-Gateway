"""WinRM method invocation and stable TLS error translation."""

from collections.abc import Callable
from typing import Any, Type


def run_winrm_method(
    session: Any,
    method_name: str,
    *args: Any,
    ssl_error_type: Type[BaseException],
    trust_error_factory: Callable[[str, str], BaseException],
    tls_error_code: str,
    tls_error_message: str,
) -> Any:
    """Run a WinRM operation while keeping TLS failures actionable and stable."""
    try:
        return getattr(session, method_name)(*args)
    except ssl_error_type as exc:
        raise trust_error_factory(tls_error_code, tls_error_message) from exc
