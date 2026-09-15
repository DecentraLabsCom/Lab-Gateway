"""Explicit dependencies for the WinRM trust-store boundary."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class WinRMTrustContext:
    """Operations and infrastructure ports for certificate trust management."""

    normalize_winrm_trust_ref: Callable[[Any], str]
    trust_http_status: Callable[[str], int]
    winrm_trust_error_payload: Callable[[Any, str], Dict[str, Any]]
    winrm_trust_ref_for_host: Callable[[Dict[str, Any]], str]
    winrm_trust_root: Callable[[], str]
    winrm_trust_file_path: Callable[[Dict[str, Any], str], str]
    winrm_trust_certificate_path: Callable[[Dict[str, Any]], str]
    winrm_trust_pem_path: Callable[[Dict[str, Any]], str]
    parse_winrm_certificate: Callable[[str], Any]
    parse_winrm_certificate_bytes: Callable[[bytes], Any]
    winrm_trust_metadata_path: Callable[[Dict[str, Any]], str]
    write_winrm_trust_bytes: Callable[[str, bytes], None]
    read_winrm_trust_metadata: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]
    write_winrm_trust_metadata: Callable[[Dict[str, Any], Dict[str, Any]], None]
    validate_winrm_certificate: Callable[
        [Any, Dict[str, Any]], Dict[str, Any]
    ]
    read_winrm_certificate_upload: Callable[[], bytes]
    winrm_trust_request_value: Callable[[str], str]
    winrm_certificate_response_metadata: Callable[
        [Any, Dict[str, Any], str], Dict[str, Any]
    ]
    store_winrm_trust_certificate: Callable[[Dict[str, Any], Any], Dict[str, Any]]
    delete_winrm_trust_certificate: Callable[[Dict[str, Any]], None]
    materialize_winrm_pem: Callable[[Dict[str, Any], Any], str]
    inspect_winrm_trust: Callable[[Dict[str, Any]], Dict[str, Any]]
    load_winrm_trust: Callable[[Dict[str, Any]], Tuple[str, Dict[str, Any]]]
    refresh_winrm_trust_store: Callable[
        [Sequence[Dict[str, Any]]], Dict[str, Dict[str, Any]]
    ]


__all__ = ["WinRMTrustContext"]
