"""Stable operational error contracts shared by the Ops Worker routes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Dict


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
