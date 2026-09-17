"""Stable operational error contracts shared by the Ops Worker routes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Dict

import requests


class WinRMTrustError(ValueError):
    """Operational error raised when a Station certificate cannot be trusted."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


WINRM_TRUST_REQUIRED_MESSAGE = "WinRM certificate trust is required"
WINRM_TRUST_REQUIRED_CODE = "WINRM_TRUST_REQUIRED"
WINRM_CERTIFICATE_INVALID_MESSAGE = "WinRM certificate trust is invalid"
WINRM_CERTIFICATE_EXPIRED_MESSAGE = "WinRM certificate is expired"
WINRM_CERTIFICATE_NOT_YET_VALID_MESSAGE = "WinRM certificate is not yet valid"
WINRM_TLS_FAILED_MESSAGE = "WinRM TLS validation failed"
WINRM_CERTIFICATE_REQUIRED_MESSAGE = "WinRM certificate file is required"
WINRM_FINGERPRINT_CONFIRMATION_REQUIRED_MESSAGE = "WinRM certificate fingerprint confirmation is required"
WINRM_FINGERPRINT_MISMATCH_MESSAGE = "WinRM certificate fingerprint confirmation does not match"
WINRM_TRUST_REF_MISMATCH_MESSAGE = "WinRM trust reference does not match the host"
WINRM_TRUST_ERROR_MESSAGES = {
    WINRM_TRUST_REQUIRED_CODE: WINRM_TRUST_REQUIRED_MESSAGE,
    "WINRM_TRUST_INVALID": WINRM_CERTIFICATE_INVALID_MESSAGE,
    "WINRM_CERTIFICATE_INVALID": WINRM_CERTIFICATE_INVALID_MESSAGE,
    "WINRM_CERTIFICATE_REQUIRED": WINRM_CERTIFICATE_REQUIRED_MESSAGE,
    "WINRM_CERTIFICATE_EXPIRED": WINRM_CERTIFICATE_EXPIRED_MESSAGE,
    "WINRM_CERTIFICATE_NOT_YET_VALID": WINRM_CERTIFICATE_NOT_YET_VALID_MESSAGE,
    "WINRM_CERTIFICATE_HOST_MISMATCH": "WinRM certificate does not match the host address",
    "WINRM_TLS_FAILED": WINRM_TLS_FAILED_MESSAGE,
    "WINRM_FINGERPRINT_CONFIRMATION_REQUIRED": WINRM_FINGERPRINT_CONFIRMATION_REQUIRED_MESSAGE,
    "WINRM_FINGERPRINT_MISMATCH": WINRM_FINGERPRINT_MISMATCH_MESSAGE,
    "WINRM_TRUST_REF_MISMATCH": WINRM_TRUST_REF_MISMATCH_MESSAGE,
    "WINRM_TRUST_STORAGE_UNAVAILABLE": "WinRM certificate trust storage is unavailable",
}

WINRM_CREDENTIALS_REQUIRED_MESSAGE = "WinRM credentials are required"
WINRM_UNREACHABLE_CODE = "WINRM_UNREACHABLE"
WINRM_UNREACHABLE_MESSAGE = "Lab Station is unreachable over WinRM"


def is_winrm_unreachable_error(exc: BaseException) -> bool:
    """Return whether an exception indicates that the Station cannot be reached."""
    network_error_types = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        ConnectionError,
        TimeoutError,
    )
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        # TLS failures are translated to the stable WinRM trust contract by
        # the command layer and must not be presented as a powered-off host.
        if isinstance(current, requests.exceptions.SSLError):
            return False
        if isinstance(current, network_error_types):
            return True
        current = current.__cause__ or current.__context__
    return False


def build_winrm_unreachable_payload(
    host_name: Any,
    host: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build the safe public payload for a Station connection failure."""
    payload: Dict[str, Any] = {
        "error": WINRM_UNREACHABLE_MESSAGE,
        "code": WINRM_UNREACHABLE_CODE,
        "host": host_name,
    }
    address = host.get("address")
    if address not in (None, ""):
        payload["address"] = address
    port = host.get("winrm_port")
    if port not in (None, ""):
        payload["port"] = port
    return payload


def is_missing_winrm_credentials_error(exc: BaseException) -> bool:
    """Return whether an exception carries the stable missing-credentials contract."""
    return isinstance(exc, ValueError) and str(exc) == WINRM_CREDENTIALS_REQUIRED_MESSAGE


def build_winrm_trust_error_payload(
    host_name: Any,
    code: str,
    *,
    request_id: Callable[[], str],
    trust_error_messages: Mapping[str, str] = WINRM_TRUST_ERROR_MESSAGES,
) -> Dict[str, Any]:
    """Build the stable public payload for a WinRM trust failure."""
    normalized_code = code if code in trust_error_messages else "WINRM_TRUST_INVALID"
    return {
        "error": trust_error_messages[normalized_code],
        "code": normalized_code,
        "host": host_name,
        "requestId": request_id(),
    }
