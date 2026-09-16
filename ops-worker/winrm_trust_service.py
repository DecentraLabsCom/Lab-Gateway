"""Dependency-injected orchestration for the WinRM trust lifecycle."""

from datetime import datetime
import logging
import os
from typing import Any, Callable, Dict, Optional, Sequence, Type

from cryptography import x509
from errors import (
    WINRM_CERTIFICATE_EXPIRED_MESSAGE,
    WINRM_CERTIFICATE_INVALID_MESSAGE,
    WINRM_CERTIFICATE_NOT_YET_VALID_MESSAGE,
    WINRM_TRUST_ERROR_MESSAGES,
    WINRM_TRUST_REQUIRED_CODE,
    WINRM_TRUST_REQUIRED_MESSAGE,
    WinRMTrustError,
)


def inspect_winrm_trust(
    host: Dict[str, Any],
    *,
    trust_ref_for_host: Callable[[Dict[str, Any]], str],
    certificate_path_for_host: Callable[[Dict[str, Any]], str],
    is_file: Callable[[str], bool],
    parse_certificate: Callable[[str], x509.Certificate],
    materialize_pem: Callable[[Dict[str, Any], x509.Certificate], str],
    certificate_metadata: Callable[[x509.Certificate, str], Dict[str, Any]],
    read_metadata: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
    validate_certificate: Callable[[x509.Certificate, Dict[str, Any]], Dict[str, Any]],
    format_datetime: Callable[[datetime], str],
    now: Callable[[], datetime],
    trust_error_type: Type[Exception] = WinRMTrustError,
) -> Dict[str, Any]:
    """Inspect one host certificate without contacting the Station."""
    trust_ref = trust_ref_for_host(host)
    path = certificate_path_for_host(host)
    if not is_file(path):
        return {
            "configured": False,
            "status": "missing",
            "errorCode": "WINRM_TRUST_REQUIRED",
            "trustRef": trust_ref,
        }
    try:
        certificate = parse_certificate(path)
        materialize_pem(host, certificate)
    except trust_error_type as exc:
        return {
            "configured": True,
            "status": "invalid",
            "errorCode": getattr(exc, "code", "WINRM_TRUST_INVALID"),
            "trustRef": trust_ref,
        }

    metadata = certificate_metadata(certificate, trust_ref)
    persisted = read_metadata(host)
    if persisted is not None:
        if persisted.get("fingerprintSha256") != metadata.get("fingerprintSha256"):
            return {
                "configured": True,
                "status": "invalid",
                "errorCode": "WINRM_TRUST_INVALID",
                "trustRef": trust_ref,
            }
        for key in ("uploadedAt", "uploadedBy", "source", "format"):
            if persisted.get(key) is not None:
                metadata[key] = persisted[key]
    try:
        validate_certificate(certificate, host)
    except trust_error_type as exc:
        error_code = getattr(exc, "code", None)
        error_code = error_code if isinstance(error_code, str) else ""
        metadata["status"] = {
            "WINRM_CERTIFICATE_EXPIRED": "expired",
            "WINRM_CERTIFICATE_NOT_YET_VALID": "not-yet-valid",
        }.get(error_code, "invalid")
        metadata["errorCode"] = getattr(exc, "code", "WINRM_TRUST_INVALID")
    metadata["host"] = host.get("name")
    metadata["address"] = host.get("address")
    metadata["lastValidatedAt"] = format_datetime(now())
    return metadata


def load_winrm_trust(
    host: Dict[str, Any],
    *,
    inspect_trust: Callable[[Dict[str, Any]], Dict[str, Any]],
    pem_path_for_host: Callable[[Dict[str, Any]], str],
    required_code: str = WINRM_TRUST_REQUIRED_CODE,
    required_message: str = WINRM_TRUST_REQUIRED_MESSAGE,
    expired_message: str = WINRM_CERTIFICATE_EXPIRED_MESSAGE,
    not_yet_valid_message: str = WINRM_CERTIFICATE_NOT_YET_VALID_MESSAGE,
    trust_error_messages: Dict[str, str] = WINRM_TRUST_ERROR_MESSAGES,
    invalid_message: str = WINRM_CERTIFICATE_INVALID_MESSAGE,
) -> tuple[str, Dict[str, Any]]:
    """Resolve a valid, non-expired certificate for one host's WinRM session."""
    metadata = inspect_trust(host)
    status = metadata.get("status")
    if not metadata.get("configured"):
        raise WinRMTrustError(required_code, required_message)
    if status == "expired":
        raise WinRMTrustError("WINRM_CERTIFICATE_EXPIRED", expired_message)
    if status == "not-yet-valid":
        raise WinRMTrustError("WINRM_CERTIFICATE_NOT_YET_VALID", not_yet_valid_message)
    if status != "ready":
        code = str(metadata.get("errorCode") or "WINRM_TRUST_INVALID")
        raise WinRMTrustError(code, trust_error_messages.get(code, invalid_message))
    return pem_path_for_host(host), metadata


def refresh_winrm_trust_store(
    hosts: Sequence[Dict[str, Any]],
    root: str,
    *,
    trust_ref_for_host: Callable[[Dict[str, Any]], str],
    inspect_trust: Callable[[Dict[str, Any]], Dict[str, Any]],
    sanitize_log_value: Callable[[Any], str],
    logger: Any = logging,
) -> Dict[str, Dict[str, Any]]:
    """Create the persistent trust layout and inspect certificates for hosts."""
    try:
        os.makedirs(root, exist_ok=True)
    except OSError as exc:
        logger.warning("Unable to create WinRM trust directory: %s", type(exc).__name__)
        return {
            str(host.get("name") or "<unknown>"): {
                "configured": False,
                "status": "unavailable",
                "errorCode": "WINRM_TRUST_STORAGE_UNAVAILABLE",
            }
            for host in hosts
        }

    result: Dict[str, Dict[str, Any]] = {}
    for host in hosts:
        name = str(host.get("name") or "<unknown>")
        try:
            trust_ref = trust_ref_for_host(host)
            os.makedirs(os.path.join(root, trust_ref), exist_ok=True)
            state = inspect_trust(host)
        except (OSError, ValueError, WinRMTrustError) as exc:
            state = {
                "configured": False,
                "status": "invalid",
                "errorCode": getattr(exc, "code", "WINRM_TRUST_INVALID"),
            }
        result[name] = state
        if state.get("status") == "ready":
            logger.info(
                "Loaded WinRM trust for host %s fingerprint=%s",
                sanitize_log_value(name),
                state.get("fingerprintSha256"),
            )
        elif state.get("status") != "missing":
            logger.warning(
                "WinRM trust unavailable for host %s status=%s code=%s",
                sanitize_log_value(name),
                state.get("status"),
                state.get("errorCode"),
            )
    return result
