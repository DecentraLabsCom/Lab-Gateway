"""Pure WinRM connection policy resolution.

The worker keeps the gateway configuration and request-facing facade.  This
module only resolves the effective connection values from explicit inputs so
the policy can be tested without importing the Flask application.
"""

from collections.abc import Callable, Collection, Mapping
from typing import Any, Optional, Tuple


def resolve_winrm_connection_policy(
    host: Mapping[str, Any],
    use_ssl: Optional[bool],
    port: Optional[int],
    transport: Optional[str],
    *,
    winrm_port: int,
    allowed_transports: Collection[str],
    coerce_bool: Callable[[Any], Optional[bool]],
) -> Tuple[bool, int, str]:
    """Resolve and validate the effective WinRM connection settings.

    ``winrm_port``, ``allowed_transports`` and ``coerce_bool`` are explicit
    dependencies so callers can supply gateway configuration while tests can
    exercise the policy in isolation.  Error messages and validation order are
    kept compatible with the historical worker helper.
    """
    if "winrm_use_ssl" not in host or "winrm_port" not in host:
        raise ValueError("host must declare winrm_use_ssl and winrm_port")
    configured_ssl = coerce_bool(host.get("winrm_use_ssl"))
    if configured_ssl is False:
        raise ValueError("WinRM HTTPS is required by gateway policy")
    effective_ssl = True

    requested_ssl = coerce_bool(use_ssl)
    if requested_ssl is not None and requested_ssl != effective_ssl:
        raise ValueError("request use_ssl does not match the host WinRM policy")

    configured_port_value = host.get("winrm_port")
    configured_port: Optional[int] = None
    if configured_port_value not in (None, ""):
        try:
            configured_port = int(configured_port_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("host winrm_port is invalid") from exc

    requested_port = None
    if port not in (None, ""):
        try:
            requested_port = int(port)
        except (TypeError, ValueError) as exc:
            raise ValueError("request port is invalid") from exc
    if configured_port is not None and configured_port != winrm_port:
        raise ValueError(f"WinRM port must be {winrm_port}")
    if configured_port is not None and requested_port is not None and requested_port != configured_port:
        raise ValueError("request port does not match the host WinRM policy")

    effective_port = requested_port or configured_port
    if effective_port is None or effective_port != winrm_port:
        raise ValueError(f"WinRM port must be {winrm_port}")

    configured_transport = str(host.get("winrm_transport") or "ntlm").strip().lower()
    effective_transport = str(transport or configured_transport).strip().lower()
    if transport not in (None, "") and effective_transport != configured_transport:
        raise ValueError("request transport does not match the host WinRM policy")
    if effective_transport not in allowed_transports:
        raise ValueError("WinRM transport is not allowed by gateway policy")
    return effective_ssl, effective_port, effective_transport
