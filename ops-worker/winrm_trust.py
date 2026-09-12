"""Pure WinRM certificate helpers.

The module deliberately contains no Flask, filesystem or inventory access.  The
entrypoint keeps the trust-store orchestration and reexports these helpers so
existing callers continue to use the historical ``worker`` names.
"""

from datetime import datetime, timezone
import ipaddress
import os
from typing import Any, Callable, Dict, List, Union

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from errors import (
    WINRM_CERTIFICATE_INVALID_MESSAGE,
    WINRM_TRUST_ERROR_MESSAGES,
    WinRMTrustError,
)


WINRM_CERTIFICATE_MAX_BYTES = 64 * 1024


def _resolve_winrm_trust_file_path(root: str, trust_ref: str, filename: str) -> str:
    """Resolve one managed trust file while keeping it under the trust root."""
    resolved_root = os.path.realpath(os.path.abspath(root))
    if not resolved_root:
        raise WinRMTrustError("WINRM_TRUST_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE)
    candidate = os.path.realpath(os.path.join(resolved_root, trust_ref, filename))
    root_prefix = os.path.join(resolved_root, "")
    if not candidate.startswith(root_prefix):
        raise WinRMTrustError("WINRM_TRUST_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE)
    return candidate


def _parse_winrm_certificate_bytes(
    raw: bytes,
    max_bytes: int = WINRM_CERTIFICATE_MAX_BYTES,
) -> x509.Certificate:
    """Parse a bounded DER or PEM certificate supplied by an operator."""
    if not raw or len(raw) > max_bytes:
        raise WinRMTrustError("WINRM_TRUST_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE)
    try:
        try:
            certificate = x509.load_der_x509_certificate(raw)
        except ValueError:
            certificate = x509.load_pem_x509_certificate(raw)
        certificate.public_key()
        return certificate
    except (ValueError, TypeError) as exc:
        raise WinRMTrustError("WINRM_TRUST_INVALID", WINRM_CERTIFICATE_INVALID_MESSAGE) from exc


def _certificate_datetime(certificate: x509.Certificate, attribute: str) -> datetime:
    """Return a certificate validity timestamp as an aware UTC datetime."""
    utc_value = getattr(certificate, f"{attribute}_utc", None)
    if utc_value is not None:
        return utc_value.astimezone(timezone.utc)
    legacy_value = getattr(certificate, attribute)
    return legacy_value.replace(tzinfo=timezone.utc)


def _format_certificate_datetime(value: datetime) -> str:
    """Serialize a certificate timestamp using the existing UTC wire format."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _dns_name_matches(pattern: Union[str, bytes], hostname: str) -> bool:
    if isinstance(pattern, bytes):
        try:
            pattern = pattern.decode("idna")
        except UnicodeError:
            return False
    normalized_pattern = str(pattern or "").strip().rstrip(".").lower()
    normalized_hostname = str(hostname or "").strip().rstrip(".").lower()
    if not normalized_pattern or not normalized_hostname:
        return False
    if normalized_pattern == normalized_hostname:
        return True
    if not normalized_pattern.startswith("*."):
        return False
    suffix = normalized_pattern[1:]
    return (
        normalized_hostname.endswith(suffix)
        and normalized_hostname.count(".") == normalized_pattern.count(".")
    )


def _is_valid_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _certificate_matches_host(certificate: x509.Certificate, host: Dict[str, Any]) -> bool:
    """Check the inventory address against SAN, falling back to the subject CN."""
    address = str(host.get("address") or "").strip().rstrip(".")
    if not address:
        return True

    san_dns_names: List[str] = []
    san_ip_addresses: List[str] = []
    san_has_values = False
    try:
        san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        san_dns_names = [str(value) for value in san.get_values_for_type(x509.DNSName)]
        san_ip_addresses = [str(value) for value in san.get_values_for_type(x509.IPAddress)]
        san_has_values = bool(san_dns_names or san_ip_addresses)
    except x509.ExtensionNotFound:
        # Certificates without SAN entries use the subject CN fallback below.
        pass

    try:
        address_ip = ipaddress.ip_address(address)
    except ValueError:
        address_ip = None

    if san_has_values:
        if address_ip is not None:
            normalized_address = str(address_ip)
            # TLS hostname verification treats an IP literal as an IP
            # identity.  A matching dNSName value is not equivalent to an
            # iPAddress SAN and would be rejected by OpenSSL/Requests.
            return any(
                str(ipaddress.ip_address(value)) == normalized_address
                for value in san_ip_addresses
                if _is_valid_ip_address(value)
            )
        return any(_dns_name_matches(value, address) for value in san_dns_names)

    common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if address_ip is not None:
        # Do not fall back to a textual CN for an IP endpoint.  WinRM uses
        # strict TLS identity checking, which requires a typed iPAddress SAN.
        return False
    return any(_dns_name_matches(attribute.value, address) for attribute in common_names)


def _winrm_certificate_metadata(
    certificate: x509.Certificate,
    trust_ref: str,
) -> Dict[str, Any]:
    """Build the public certificate metadata without touching external state."""
    not_before = _certificate_datetime(certificate, "not_valid_before")
    not_after = _certificate_datetime(certificate, "not_valid_after")
    san_dns_names: List[str] = []
    san_ip_addresses: List[str] = []
    try:
        san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        san_dns_names = [str(value) for value in san.get_values_for_type(x509.DNSName)]
        san_ip_addresses = [str(value) for value in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        # A certificate without a SAN is still parseable; report empty SAN metadata.
        pass

    now = datetime.now(timezone.utc)
    status = "ready"
    error_code = None
    if now < not_before:
        status = "not-yet-valid"
        error_code = "WINRM_CERTIFICATE_NOT_YET_VALID"
    elif now > not_after:
        status = "expired"
        error_code = "WINRM_CERTIFICATE_EXPIRED"

    metadata: Dict[str, Any] = {
        "configured": True,
        "status": status,
        "trustRef": trust_ref,
        "fingerprintSha256": certificate.fingerprint(hashes.SHA256()).hex().upper(),
        "fingerprintSha1": certificate.fingerprint(hashes.SHA1()).hex().upper(),
        "subject": certificate.subject.rfc4514_string(),
        "issuer": certificate.issuer.rfc4514_string(),
        "sanDnsNames": san_dns_names,
        "sanIpAddresses": san_ip_addresses,
        "notBefore": _format_certificate_datetime(not_before),
        "notAfter": _format_certificate_datetime(not_after),
        "selfSigned": certificate.subject == certificate.issuer,
    }
    if error_code:
        metadata["errorCode"] = error_code
    return metadata


def validate_winrm_certificate(
    certificate: x509.Certificate,
    host: Dict[str, Any],
    trust_ref: str,
    *,
    certificate_matches_host: Callable[[x509.Certificate, Dict[str, Any]], bool] = _certificate_matches_host,
    certificate_metadata: Callable[[x509.Certificate, str], Dict[str, Any]] = _winrm_certificate_metadata,
    trust_error_messages: Dict[str, str] = WINRM_TRUST_ERROR_MESSAGES,
    invalid_message: str = WINRM_CERTIFICATE_INVALID_MESSAGE,
) -> Dict[str, Any]:
    """Validate server trust for exactly one inventory host."""
    try:
        eku = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        if ExtendedKeyUsageOID.SERVER_AUTH not in eku:
            raise WinRMTrustError("WINRM_CERTIFICATE_INVALID", invalid_message)
    except x509.ExtensionNotFound:
        # Windows-generated self-signed WinRM certificates may omit EKU.
        pass

    if not certificate_matches_host(certificate, host):
        raise WinRMTrustError(
            "WINRM_CERTIFICATE_HOST_MISMATCH",
            trust_error_messages["WINRM_CERTIFICATE_HOST_MISMATCH"],
        )

    metadata = certificate_metadata(certificate, trust_ref)
    if metadata["status"] != "ready":
        raise WinRMTrustError(
            metadata["errorCode"],
            trust_error_messages.get(metadata["errorCode"], invalid_message),
        )
    return metadata
