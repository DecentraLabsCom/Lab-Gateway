from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from winrm_trust_operations import (
    delete_trust_certificate,
    read_certificate_upload,
    store_trust_certificate,
    trust_http_status,
)


class _TrustError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def test_certificate_upload_rejects_unsupported_extension_before_reading():
    uploaded = Mock(filename="certificate.txt")
    files = {"certificate": uploaded}

    with pytest.raises(_TrustError) as raised:
        read_certificate_upload(
            files=files,
            content_length=None,
            body_reader=Mock(),
            max_bytes=1024,
            allowed_extensions={".cer", ".der", ".pem"},
            secure_filename=lambda value: value,
            trust_error_type=_TrustError,
            required_code="REQUIRED",
            required_message="required",
            invalid_code="INVALID",
            invalid_message="invalid",
        )

    assert raised.value.code == "INVALID"
    uploaded.stream.read.assert_not_called()


def test_store_projects_metadata_and_uses_managed_paths():
    certificate = Mock()
    certificate.public_bytes.return_value = b"der-bytes"
    write_bytes = Mock()
    write_metadata = Mock()
    materialize_pem = Mock(return_value="pem-path")
    inspect_trust = Mock(return_value={"configured": True})
    response_metadata = Mock(return_value={"fingerprint": "AA:BB"})

    result = store_trust_certificate(
        {"name": "lab-ws-01"},
        certificate,
        response_metadata=response_metadata,
        write_bytes=write_bytes,
        certificate_path_for_host=lambda _host: "/trust/cert.der",
        write_metadata=write_metadata,
        materialize_pem=materialize_pem,
        inspect_trust=inspect_trust,
        format_datetime=lambda value: value.isoformat(),
        now=lambda: datetime(2026, 9, 14, tzinfo=timezone.utc),
    )

    assert result == {"configured": True}
    assert response_metadata.call_args.args[2] == "DER"
    metadata = response_metadata.return_value
    assert metadata["uploadedBy"] == "lab-manager"
    assert metadata["source"] == "lab-manager"
    write_bytes.assert_called_once()
    assert write_bytes.call_args.args == ("/trust/cert.der", b"der-bytes")
    write_metadata.assert_called_once()
    materialize_pem.assert_called_once_with({"name": "lab-ws-01"}, certificate)
    inspect_trust.assert_called_once_with({"name": "lab-ws-01"})


def test_trust_http_status_preserves_public_mapping():
    assert trust_http_status("WINRM_TRUST_STORAGE_UNAVAILABLE") == 503
    assert trust_http_status("WINRM_CERTIFICATE_EXPIRED") == 422
    assert trust_http_status("WINRM_TRUST_INVALID") == 400


def test_delete_removes_all_managed_artifacts():
    delete_files = Mock()

    delete_trust_certificate(
        {"name": "lab-ws-01"},
        file_path_for_host=lambda _host, filename: f"/trust/{filename}",
        certificate_name="certificate.der",
        pem_name="trust.pem",
        metadata_name="metadata.json",
        delete_files=delete_files,
    )

    delete_files.assert_called_once_with(
        ["/trust/certificate.der", "/trust/trust.pem", "/trust/metadata.json"]
    )
