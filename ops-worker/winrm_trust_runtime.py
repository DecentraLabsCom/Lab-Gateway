"""Composition adapter for the WinRM trust lifecycle."""

from collections.abc import Mapping, Sequence
from typing import Any, Dict, Optional, Tuple


class WinRMTrustRuntime:
    """Resolve trust-store operations from a live worker provider namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def normalize_winrm_trust_ref(self, value: Any) -> str:
        get = self._get
        return get("_normalize_trust_ref_impl")(
            value,
            secure_filename=get("secure_filename"),
            trust_ref_pattern=get("WINRM_TRUST_REF_RE"),
        )

    def trust_http_status(self, code: str) -> int:
        return self._get("_trust_http_status_impl")(code)

    def winrm_trust_error_payload(self, host_name: Any, code: str) -> Dict[str, Any]:
        get = self._get
        return get("_build_winrm_trust_error_payload_impl")(
            host_name,
            code,
            request_id=get("_request_id"),
            trust_error_messages=get("WINRM_TRUST_ERROR_MESSAGES"),
        )

    def winrm_trust_ref_for_host(self, host: Dict[str, Any]) -> str:
        return self._get("_trust_ref_for_host_impl")(
            host,
            normalize_ref=self._get("normalize_winrm_trust_ref"),
        )

    def winrm_trust_root(self) -> str:
        get = self._get
        return get("_resolve_trust_root_impl")(
            get("OPS_WINRM_TRUST_PATH"),
            realpath=get("os").path.realpath,
            abspath=get("os").path.abspath,
            trust_error_type=get("WinRMTrustError"),
            invalid_message=get("WINRM_CERTIFICATE_INVALID_MESSAGE"),
        )

    def winrm_trust_file_path(self, host: Dict[str, Any], filename: str) -> str:
        get = self._get
        return get("_resolve_trust_file_path_impl")(
            host,
            filename,
            root=get("_winrm_trust_root")(),
            trust_ref_for_host=get("winrm_trust_ref_for_host"),
            resolve_path=get("_resolve_winrm_trust_file_path"),
        )

    def winrm_trust_certificate_path(self, host: Dict[str, Any]) -> str:
        return self._get("_winrm_trust_file_path")(
            host,
            self._get("WINRM_TRUST_CERTIFICATE_NAME"),
        )

    def winrm_trust_pem_path(self, host: Dict[str, Any]) -> str:
        return self._get("_winrm_trust_file_path")(
            host,
            self._get("WINRM_TRUST_PEM_NAME"),
        )

    def parse_winrm_certificate(self, path: str) -> Any:
        get = self._get
        return get("_read_trust_certificate_impl")(
            path,
            max_bytes=get("WINRM_CERTIFICATE_MAX_BYTES"),
            parse_certificate_bytes=get("_parse_winrm_certificate_bytes"),
        )

    def parse_winrm_certificate_bytes(self, raw: bytes) -> Any:
        return self._get("_parse_winrm_certificate_bytes_impl")(
            raw,
            max_bytes=self._get("WINRM_CERTIFICATE_MAX_BYTES"),
        )

    def winrm_trust_metadata_path(self, host: Dict[str, Any]) -> str:
        return self._get("_winrm_trust_file_path")(
            host,
            self._get("WINRM_TRUST_METADATA_NAME"),
        )

    def write_winrm_trust_bytes(self, path: str, content: bytes) -> None:
        return self._get("_write_trust_bytes_impl")(path, content)

    def read_winrm_trust_metadata(self, host: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._get("_read_trust_metadata_file")(
            self._get("_winrm_trust_metadata_path")(host)
        )

    def write_winrm_trust_metadata(
        self,
        host: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> None:
        get = self._get
        return get("_write_trust_metadata_file")(
            get("_winrm_trust_metadata_path")(host),
            metadata,
            write_bytes=get("_write_winrm_trust_bytes"),
        )

    def validate_winrm_certificate(self, certificate: Any, host: Dict[str, Any]) -> Dict[str, Any]:
        get = self._get
        return get("_validate_winrm_certificate_impl")(
            certificate,
            host,
            get("winrm_trust_ref_for_host")(host),
            certificate_matches_host=get("_certificate_matches_host"),
            certificate_metadata=get("_winrm_certificate_metadata"),
            trust_error_messages=get("WINRM_TRUST_ERROR_MESSAGES"),
            invalid_message=get("WINRM_CERTIFICATE_INVALID_MESSAGE"),
        )

    def read_winrm_certificate_upload(self) -> bytes:
        get = self._get
        request = get("request")
        return get("_read_certificate_upload_impl")(
            files=request.files,
            content_length=request.content_length,
            body_reader=lambda: request.get_data(cache=False, as_text=False),
            max_bytes=get("WINRM_CERTIFICATE_MAX_BYTES"),
            allowed_extensions=get("WINRM_CERTIFICATE_EXTENSIONS"),
            secure_filename=get("secure_filename"),
            trust_error_type=get("WinRMTrustError"),
            required_code="WINRM_CERTIFICATE_REQUIRED",
            required_message=get("WINRM_CERTIFICATE_REQUIRED_MESSAGE"),
            invalid_code="WINRM_TRUST_INVALID",
            invalid_message=get("WINRM_CERTIFICATE_INVALID_MESSAGE"),
        )

    def winrm_trust_request_value(self, name: str) -> str:
        request = self._get("request")
        return self._get("_trust_request_value_impl")(
            name,
            form=request.form,
            is_json=request.is_json,
            json_payload=request.get_json(silent=True) if request.is_json else None,
        )

    def winrm_certificate_response_metadata(
        self,
        certificate: Any,
        host: Dict[str, Any],
        input_format: str,
    ) -> Dict[str, Any]:
        get = self._get
        return get("_certificate_response_metadata_impl")(
            certificate,
            host,
            input_format,
            trust_ref_for_host=get("winrm_trust_ref_for_host"),
            certificate_metadata=get("_winrm_certificate_metadata"),
        )

    def store_winrm_trust_certificate(
        self,
        host: Dict[str, Any],
        certificate: Any,
    ) -> Dict[str, Any]:
        get = self._get
        return get("_store_trust_certificate_impl")(
            host,
            certificate,
            response_metadata=get("_winrm_certificate_response_metadata"),
            write_bytes=get("_write_winrm_trust_bytes"),
            certificate_path_for_host=get("winrm_trust_certificate_path"),
            write_metadata=get("_write_winrm_trust_metadata"),
            materialize_pem=get("_materialize_winrm_pem"),
            inspect_trust=get("inspect_winrm_trust"),
            format_datetime=get("_format_certificate_datetime"),
            now=lambda: get("datetime").now(get("timezone").utc),
        )

    def delete_winrm_trust_certificate(self, host: Dict[str, Any]) -> None:
        get = self._get
        return get("_delete_trust_certificate_impl")(
            host,
            file_path_for_host=get("_winrm_trust_file_path"),
            certificate_name=get("WINRM_TRUST_CERTIFICATE_NAME"),
            pem_name=get("WINRM_TRUST_PEM_NAME"),
            metadata_name=get("WINRM_TRUST_METADATA_NAME"),
            delete_files=get("_delete_trust_files_impl"),
        )

    def materialize_winrm_pem(self, host: Dict[str, Any], certificate: Any) -> str:
        get = self._get
        return get("_materialize_trust_pem_impl")(
            get("winrm_trust_pem_path")(host),
            certificate,
            max_bytes=get("WINRM_CERTIFICATE_MAX_BYTES"),
        )

    def inspect_winrm_trust(self, host: Dict[str, Any]) -> Dict[str, Any]:
        get = self._get
        return get("_inspect_winrm_trust_impl")(
            host,
            trust_ref_for_host=get("winrm_trust_ref_for_host"),
            certificate_path_for_host=get("winrm_trust_certificate_path"),
            is_file=get("os").path.isfile,
            parse_certificate=get("_parse_winrm_certificate"),
            materialize_pem=get("_materialize_winrm_pem"),
            certificate_metadata=get("_winrm_certificate_metadata"),
            read_metadata=get("_read_winrm_trust_metadata"),
            validate_certificate=get("_validate_winrm_certificate"),
            format_datetime=get("_format_certificate_datetime"),
            now=lambda: get("datetime").now(get("timezone").utc),
            trust_error_type=get("WinRMTrustError"),
        )

    def load_winrm_trust(self, host: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        get = self._get
        return get("_load_winrm_trust_impl")(
            host,
            inspect_trust=get("inspect_winrm_trust"),
            pem_path_for_host=get("winrm_trust_pem_path"),
            required_code=get("WINRM_TRUST_REQUIRED_CODE"),
            required_message=get("WINRM_TRUST_REQUIRED_MESSAGE"),
            expired_message=get("WINRM_CERTIFICATE_EXPIRED_MESSAGE"),
            not_yet_valid_message=get("WINRM_CERTIFICATE_NOT_YET_VALID_MESSAGE"),
            trust_error_messages=get("WINRM_TRUST_ERROR_MESSAGES"),
            invalid_message=get("WINRM_CERTIFICATE_INVALID_MESSAGE"),
        )

    def refresh_winrm_trust_store(
        self,
        hosts: Sequence[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        get = self._get
        return get("_refresh_winrm_trust_store_impl")(
            hosts,
            get("_winrm_trust_root")(),
            trust_ref_for_host=get("winrm_trust_ref_for_host"),
            inspect_trust=get("inspect_winrm_trust"),
            sanitize_log_value=get("_sanitize_log_value"),
            logger=get("logging"),
        )


def create_winrm_trust_runtime(providers: Mapping[str, Any]) -> WinRMTrustRuntime:
    """Create a trust adapter bound to live worker providers."""
    return WinRMTrustRuntime(providers)


__all__ = ["WinRMTrustRuntime", "create_winrm_trust_runtime"]
