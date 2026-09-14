"""HTTP-adjacent WinRM trust operations with bounded I/O and managed paths."""

import os
from collections.abc import Callable, Collection, Mapping
from datetime import datetime
from typing import Any, Dict, Optional, Type

from cryptography.hazmat.primitives import serialization


def read_certificate_upload(
    *,
    files: Any,
    content_length: Optional[int],
    body_reader: Callable[[], bytes],
    max_bytes: int,
    allowed_extensions: Collection[str],
    secure_filename: Callable[[str], str],
    trust_error_type: Type[BaseException],
    required_code: str,
    required_message: str,
    invalid_code: str,
    invalid_message: str,
) -> bytes:
    """Read a certificate from multipart or raw input without unbounded data."""
    uploaded = files.get("certificate") or files.get("file")
    if uploaded is not None:
        filename = str(uploaded.filename or "").strip()
        if filename:
            extension = os.path.splitext(secure_filename(filename))[1].lower()
            if extension not in allowed_extensions:
                raise trust_error_type(invalid_code, invalid_message)
        raw = uploaded.stream.read(max_bytes + 1)
    else:
        if content_length and content_length > max_bytes:
            raise trust_error_type(invalid_code, invalid_message)
        raw = body_reader()
    if not raw:
        raise trust_error_type(required_code, required_message)
    if len(raw) > max_bytes:
        raise trust_error_type(invalid_code, invalid_message)
    return raw


def request_value(
    name: str,
    *,
    form: Mapping[str, Any],
    is_json: bool,
    json_payload: Optional[Mapping[str, Any]],
) -> str:
    value = form.get(name)
    if value is not None:
        return str(value).strip()
    if is_json:
        return str((json_payload or {}).get(name) or "").strip()
    return ""


def certificate_response_metadata(
    certificate: Any,
    host: Mapping[str, Any],
    input_format: str,
    *,
    trust_ref_for_host: Callable[[Mapping[str, Any]], str],
    certificate_metadata: Callable[[Any, str], Dict[str, Any]],
) -> Dict[str, Any]:
    metadata = certificate_metadata(certificate, trust_ref_for_host(host))
    metadata["host"] = host.get("name")
    metadata["address"] = host.get("address")
    metadata["format"] = input_format
    return metadata


def store_trust_certificate(
    host: Mapping[str, Any],
    certificate: Any,
    *,
    response_metadata: Callable[[Any, Mapping[str, Any], str], Dict[str, Any]],
    write_bytes: Callable[[str, bytes], None],
    certificate_path_for_host: Callable[[Mapping[str, Any]], str],
    write_metadata: Callable[[Mapping[str, Any], Dict[str, Any]], None],
    materialize_pem: Callable[[Mapping[str, Any], Any], str],
    inspect_trust: Callable[[Mapping[str, Any]], Dict[str, Any]],
    format_datetime: Callable[[datetime], str],
    now: Callable[[], datetime],
) -> Dict[str, Any]:
    metadata = response_metadata(certificate, host, "DER")
    metadata.update(
        {
            "uploadedAt": format_datetime(now()),
            "uploadedBy": "lab-manager",
            "source": "lab-manager",
        }
    )
    write_bytes(
        certificate_path_for_host(host),
        certificate.public_bytes(serialization.Encoding.DER),
    )
    write_metadata(host, metadata)
    materialize_pem(host, certificate)
    return inspect_trust(host)


def delete_trust_certificate(
    host: Mapping[str, Any],
    *,
    file_path_for_host: Callable[[Mapping[str, Any], str], str],
    certificate_name: str,
    pem_name: str,
    metadata_name: str,
    delete_files: Callable[[list[str]], None],
) -> None:
    delete_files(
        [
            file_path_for_host(host, certificate_name),
            file_path_for_host(host, pem_name),
            file_path_for_host(host, metadata_name),
        ]
    )


def trust_http_status(code: str) -> int:
    if code == "WINRM_TRUST_STORAGE_UNAVAILABLE":
        return 503
    if code in {
        "WINRM_CERTIFICATE_HOST_MISMATCH",
        "WINRM_CERTIFICATE_EXPIRED",
        "WINRM_CERTIFICATE_NOT_YET_VALID",
        "WINRM_FINGERPRINT_MISMATCH",
        "WINRM_TRUST_REF_MISMATCH",
    }:
        return 422
    return 400


__all__ = [
    "certificate_response_metadata",
    "delete_trust_certificate",
    "read_certificate_upload",
    "request_value",
    "store_trust_certificate",
    "trust_http_status",
]
