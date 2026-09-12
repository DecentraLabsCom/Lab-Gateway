from datetime import datetime, timedelta, timezone
import ipaddress
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

import errors
import winrm_trust
import winrm_trust_store
import worker


def _certificate(address: str = "192.168.1.50") -> x509.Certificate:
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, address)])
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
    )
    san = (
        x509.IPAddress(ipaddress.ip_address(address))
        if "." in address and address.replace(".", "").isdigit()
        else x509.DNSName(address)
    )
    return builder.add_extension(
        x509.SubjectAlternativeName([san]), critical=False
    ).sign(private_key, hashes.SHA256())


def test_certificate_metadata_and_host_matching_are_exposed_by_the_trust_module():
    certificate = _certificate()

    metadata = winrm_trust._winrm_certificate_metadata(certificate, "pc-siemens")

    assert metadata["status"] == "ready"
    assert metadata["trustRef"] == "pc-siemens"
    assert len(metadata["fingerprintSha256"]) == 64
    assert metadata["sanIpAddresses"] == ["192.168.1.50"]
    assert winrm_trust._certificate_matches_host(certificate, {"address": "192.168.1.50"}) is True
    assert winrm_trust._certificate_matches_host(certificate, {"address": "192.168.1.51"}) is False


def test_certificate_datetime_format_is_utc_and_stable():
    value = datetime(2026, 9, 12, 10, 11, 12, 345678, tzinfo=timezone(timedelta(hours=2)))

    assert winrm_trust._format_certificate_datetime(value) == "2026-09-12T08:11:12.345678Z"


def test_worker_keeps_the_historical_private_helper_aliases():
    assert worker._certificate_datetime is winrm_trust._certificate_datetime
    assert worker._certificate_matches_host is winrm_trust._certificate_matches_host
    assert worker._dns_name_matches is winrm_trust._dns_name_matches
    assert worker._format_certificate_datetime is winrm_trust._format_certificate_datetime
    assert worker._is_valid_ip_address is winrm_trust._is_valid_ip_address
    assert worker._winrm_certificate_metadata is winrm_trust._winrm_certificate_metadata


def test_certificate_parser_accepts_der_and_pem_and_keeps_the_size_guard():
    certificate = _certificate()
    der = certificate.public_bytes(serialization.Encoding.DER)
    pem = certificate.public_bytes(serialization.Encoding.PEM)

    assert winrm_trust._parse_winrm_certificate_bytes(der).fingerprint(hashes.SHA256()) == certificate.fingerprint(
        hashes.SHA256()
    )
    assert winrm_trust._parse_winrm_certificate_bytes(pem).fingerprint(hashes.SHA256()) == certificate.fingerprint(
        hashes.SHA256()
    )
    with pytest.raises(errors.WinRMTrustError) as error:
        winrm_trust._parse_winrm_certificate_bytes(b"x" * (winrm_trust.WINRM_CERTIFICATE_MAX_BYTES + 1))
    assert error.value.code == "WINRM_TRUST_INVALID"


def test_trust_file_path_resolves_under_the_configured_root():
    root = os.path.realpath(os.getcwd())

    resolved = winrm_trust._resolve_winrm_trust_file_path(root, "pc-siemens", "server.cer")

    assert resolved == os.path.join(root, "pc-siemens", "server.cer")
    with pytest.raises(errors.WinRMTrustError) as error:
        winrm_trust._resolve_winrm_trust_file_path(root, "pc-siemens", os.path.join("..", "..", "outside"))
    assert error.value.code == "WINRM_TRUST_INVALID"


def test_trust_store_persists_bytes_atomically_and_round_trips_metadata(tmp_path):
    certificate_path = tmp_path / "pc-siemens" / "server.cer"
    metadata_path = tmp_path / "pc-siemens" / "metadata.json"

    winrm_trust_store.write_trust_bytes(str(certificate_path), b"certificate")
    winrm_trust_store.write_trust_metadata(
        str(metadata_path), {"status": "ready", "trustRef": "pc-siemens"}
    )

    assert certificate_path.read_bytes() == b"certificate"
    assert winrm_trust_store.read_trust_metadata(str(metadata_path)) == {
        "status": "ready",
        "trustRef": "pc-siemens",
    }
    assert winrm_trust_store.read_trust_metadata(str(tmp_path / "missing.json")) is None


def test_trust_store_returns_empty_metadata_for_invalid_json(tmp_path):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("not-json", encoding="utf-8")

    assert winrm_trust_store.read_trust_metadata(str(metadata_path)) == {}


def test_trust_store_materializes_a_pem_copy_and_deletes_managed_files(tmp_path):
    certificate = _certificate()
    pem_path = tmp_path / "server.pem"
    managed_paths = [
        tmp_path / "server.cer",
        pem_path,
        tmp_path / "metadata.json",
    ]
    for path in managed_paths:
        path.write_bytes(b"managed")

    assert winrm_trust_store.materialize_trust_pem(str(pem_path), certificate, max_bytes=64 * 1024) == str(pem_path)
    assert pem_path.read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")

    winrm_trust_store.delete_trust_files([str(path) for path in managed_paths])
    winrm_trust_store.delete_trust_files([str(path) for path in managed_paths])
    assert all(not path.exists() for path in managed_paths)


def test_certificate_validation_composition_preserves_host_and_status_contracts():
    certificate = _certificate()
    host = {"name": "PC-Siemens", "address": "192.168.1.50"}

    metadata = winrm_trust.validate_winrm_certificate(certificate, host, "pc-siemens")

    assert metadata["status"] == "ready"
    assert metadata["trustRef"] == "pc-siemens"
    with pytest.raises(errors.WinRMTrustError) as error:
        winrm_trust.validate_winrm_certificate(
            certificate,
            {"name": "PC-Siemens", "address": "192.168.1.51"},
            "pc-siemens",
        )
    assert error.value.code == "WINRM_CERTIFICATE_HOST_MISMATCH"
