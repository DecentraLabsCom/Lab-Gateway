"""Composition adapter for the WinRM trust-store lifecycle."""

from collections.abc import Sequence
from typing import Any, Dict, List, Optional, Tuple

from winrm_trust_context import WinRMTrustContext


class WinRMTrustRuntime:
    """Expose trust-store operations through explicit ports."""

    def __init__(self, context: WinRMTrustContext):
        self._context = context

    def normalize_winrm_trust_ref(self, value: Any) -> str:
        return self._context.normalize_winrm_trust_ref(value)

    def trust_http_status(self, code: str) -> int:
        return self._context.trust_http_status(code)

    def winrm_trust_error_payload(self, host_name: Any, code: str) -> Dict[str, Any]:
        return self._context.winrm_trust_error_payload(host_name, code)

    def winrm_trust_ref_for_host(self, host: Dict[str, Any]) -> str:
        return self._context.winrm_trust_ref_for_host(host)

    def winrm_trust_root(self) -> str:
        return self._context.winrm_trust_root()

    def winrm_trust_file_path(self, host: Dict[str, Any], filename: str) -> str:
        return self._context.winrm_trust_file_path(host, filename)

    def winrm_trust_certificate_path(self, host: Dict[str, Any]) -> str:
        return self._context.winrm_trust_certificate_path(host)

    def winrm_trust_pem_path(self, host: Dict[str, Any]) -> str:
        return self._context.winrm_trust_pem_path(host)

    def parse_winrm_certificate(self, path: str) -> Any:
        return self._context.parse_winrm_certificate(path)

    def parse_winrm_certificate_bytes(self, raw: bytes) -> Any:
        return self._context.parse_winrm_certificate_bytes(raw)

    def winrm_trust_metadata_path(self, host: Dict[str, Any]) -> str:
        return self._context.winrm_trust_metadata_path(host)

    def write_winrm_trust_bytes(self, path: str, content: bytes) -> None:
        return self._context.write_winrm_trust_bytes(path, content)

    def read_winrm_trust_metadata(self, host: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._context.read_winrm_trust_metadata(host)

    def write_winrm_trust_metadata(
        self,
        host: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> None:
        return self._context.write_winrm_trust_metadata(host, metadata)

    def validate_winrm_certificate(
        self,
        certificate: Any,
        host: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._context.validate_winrm_certificate(certificate, host)

    def read_winrm_certificate_upload(self) -> bytes:
        return self._context.read_winrm_certificate_upload()

    def winrm_trust_request_value(self, name: str) -> str:
        return self._context.winrm_trust_request_value(name)

    def winrm_certificate_response_metadata(
        self,
        certificate: Any,
        host: Dict[str, Any],
        input_format: str,
    ) -> Dict[str, Any]:
        return self._context.winrm_certificate_response_metadata(
            certificate,
            host,
            input_format,
        )

    def store_winrm_trust_certificate(
        self,
        host: Dict[str, Any],
        certificate: Any,
    ) -> Dict[str, Any]:
        return self._context.store_winrm_trust_certificate(host, certificate)

    def delete_winrm_trust_certificate(self, host: Dict[str, Any]) -> None:
        return self._context.delete_winrm_trust_certificate(host)

    def materialize_winrm_pem(self, host: Dict[str, Any], certificate: Any) -> str:
        return self._context.materialize_winrm_pem(host, certificate)

    def inspect_winrm_trust(self, host: Dict[str, Any]) -> Dict[str, Any]:
        return self._context.inspect_winrm_trust(host)

    def load_winrm_trust(self, host: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        return self._context.load_winrm_trust(host)

    def refresh_winrm_trust_store(
        self,
        hosts: Sequence[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        return self._context.refresh_winrm_trust_store(hosts)


def create_winrm_trust_runtime(context: WinRMTrustContext) -> WinRMTrustRuntime:
    """Create a trust runtime bound to explicit ports."""
    return WinRMTrustRuntime(context)


__all__ = ["WinRMTrustRuntime", "create_winrm_trust_runtime"]
