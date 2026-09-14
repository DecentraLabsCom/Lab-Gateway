import io
import json
import os
import ssl
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def make_winrm_certificate(address="192.168.1.50", *, expired=False, ip_as_dns=False):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    not_before = now - timedelta(days=30)
    not_after = now - timedelta(days=1) if expired else now + timedelta(days=365)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "LAB-WS-01"),
    ])
    san_values: list[x509.GeneralName] = [x509.DNSName("LAB-WS-01")]
    san_values.append(x509.DNSName(address) if ip_as_dns else x509.IPAddress(worker.ipaddress.ip_address(address)))
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            x509.SubjectAlternativeName([
                *san_values,
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.DER)


def test_run_labstation_command_requires_credentials():
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    try:
        worker.run_labstation_command(host, "status-json", [], None, None, None, None, None)
        assert False, "Expected ValueError when credentials are missing"
    except ValueError as exc:
        assert "WinRM credentials are required" in str(exc)


def test_winrm_defaults_to_https_and_rejects_plaintext():
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }
    endpoint = worker.winrm_endpoint(host, None, None)
    assert endpoint == "https://192.168.1.50:5986/wsman"
    try:
        worker.winrm_endpoint(host, False, 5985)
        assert False, "Expected plaintext WinRM to be rejected"
    except ValueError as exc:
        assert "HTTPS" in str(exc) or "use_ssl" in str(exc)


def test_winrm_request_cannot_override_host_transport_or_port():
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }
    try:
        worker._winrm_connection_policy(host, True, 5985, "ntlm")
        assert False, "Expected host port policy rejection"
    except ValueError as exc:
        assert "port" in str(exc)
    try:
        worker._winrm_connection_policy(host, True, 5986, "kerberos")
        assert False, "Expected host transport policy rejection"
    except ValueError as exc:
        assert "transport" in str(exc)


def test_winrm_trust_reference_rejects_path_traversal_components():
    with pytest.raises(ValueError, match="winrm_trust_ref"):
        worker.normalize_winrm_trust_ref("station..\\..\\outside")

    with pytest.raises(ValueError, match="winrm_trust_ref"):
        worker.normalize_winrm_trust_ref("station..outside")


def test_winrm_catalog_fails_closed_on_transport_or_management_vlan():
    secure_host = {
        "name": "lab-ws-01",
        "address": "10.7.74.10",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }
    original_cidrs = worker.WINRM_MANAGEMENT_CIDRS
    try:
        worker.WINRM_MANAGEMENT_CIDRS = []
        with pytest.raises(ValueError, match="WINRM_MANAGEMENT_CIDRS"):
            worker.validate_winrm_catalog({"hosts": [secure_host]})

        worker.WINRM_MANAGEMENT_CIDRS = ["10.7.74.0/24"]
        worker.validate_winrm_catalog({"hosts": [secure_host]})

        insecure_host = {**secure_host, "winrm_use_ssl": False, "winrm_port": 5985}
        with pytest.raises(ValueError, match="HTTPS"):
            worker.validate_winrm_catalog({"hosts": [insecure_host]})

        outside_host = {**secure_host, "address": "10.7.75.10"}
        with pytest.raises(ValueError, match="WINRM_MANAGEMENT_CIDRS"):
            worker.validate_winrm_catalog({"hosts": [outside_host]})
    finally:
        worker.WINRM_MANAGEMENT_CIDRS = original_cidrs


def test_winrm_trust_store_discovers_certificate_for_host(tmp_path, monkeypatch):
    certificate_dir = tmp_path / "pc-siemens"
    certificate_dir.mkdir()
    (certificate_dir / "server.cer").write_bytes(make_winrm_certificate())
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))

    host = {
        "name": "PC-Siemens",
        "address": "192.168.1.50",
        "winrm_trust_ref": "pc-siemens",
    }
    result = worker.refresh_winrm_trust_store([host])

    assert result["PC-Siemens"]["configured"] is True
    assert result["PC-Siemens"]["status"] == "ready"
    assert result["PC-Siemens"]["trustRef"] == "pc-siemens"
    assert len(result["PC-Siemens"]["fingerprintSha256"]) == 64
    assert result["PC-Siemens"]["sanIpAddresses"] == ["192.168.1.50"]


def test_winrm_session_uses_host_certificate_and_keeps_validation_enabled(tmp_path, monkeypatch):
    certificate_dir = tmp_path / "pc-siemens"
    certificate_dir.mkdir()
    (certificate_dir / "server.cer").write_bytes(make_winrm_certificate())
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))
    monkeypatch.setattr(worker, "_winrm_credentials", lambda *args: ("user", "password"))

    session = MagicMock()
    session.run_ps.return_value.status_code = 0
    session.run_ps.return_value.std_out = b"ok"
    session_factory = patch("worker.winrm.Session", return_value=session)
    host = {
        "name": "PC-Siemens",
        "address": "192.168.1.50",
        "winrm_trust_ref": "pc-siemens",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }
    with session_factory as mock_session:
        worker.run_remote_powershell(host, "Write-Output ok", None, None, None, None, None)

    kwargs = mock_session.call_args.kwargs
    assert kwargs["ca_trust_path"] == str(certificate_dir / "server.pem")
    assert kwargs["server_cert_validation"] == "validate"
    assert (certificate_dir / "server.pem").read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
    ssl.create_default_context(cafile=str(certificate_dir / "server.pem"))


def test_winrm_session_requires_host_certificate(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))
    monkeypatch.setattr(worker, "_winrm_credentials", lambda *args: ("user", "password"))
    host = {
        "name": "PC-Siemens",
        "address": "192.168.1.50",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }

    with pytest.raises(worker.WinRMTrustError) as exc_info:
        worker.run_remote_powershell(host, "Write-Output ok", None, None, None, None, None)

    assert exc_info.value.code == "WINRM_TRUST_REQUIRED"


def test_winrm_tls_failure_is_classified(tmp_path, monkeypatch):
    certificate_dir = tmp_path / "pc-siemens"
    certificate_dir.mkdir()
    (certificate_dir / "server.cer").write_bytes(make_winrm_certificate())
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))
    monkeypatch.setattr(worker, "_winrm_credentials", lambda *args: ("user", "password"))
    session = MagicMock()
    session.run_ps.side_effect = worker.requests.exceptions.SSLError("certificate verify failed")
    host = {
        "name": "PC-Siemens",
        "address": "192.168.1.50",
        "winrm_trust_ref": "pc-siemens",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }

    with patch("worker.winrm.Session", return_value=session), pytest.raises(worker.WinRMTrustError) as exc_info:
        worker.run_remote_powershell(host, "Write-Output ok", None, None, None, None, None)

    assert exc_info.value.code == "WINRM_TLS_FAILED"


def test_winrm_trust_store_reports_expired_certificate(tmp_path, monkeypatch):
    certificate_dir = tmp_path / "pc-siemens"
    certificate_dir.mkdir()
    (certificate_dir / "server.cer").write_bytes(make_winrm_certificate(expired=True))
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))

    result = worker.refresh_winrm_trust_store([{
        "name": "PC-Siemens",
        "address": "192.168.1.50",
        "winrm_trust_ref": "pc-siemens",
    }])

    assert result["PC-Siemens"]["configured"] is True
    assert result["PC-Siemens"]["status"] == "expired"
    assert result["PC-Siemens"]["errorCode"] == "WINRM_CERTIFICATE_EXPIRED"


def test_winrm_trust_store_reports_certificate_host_mismatch(tmp_path, monkeypatch):
    certificate_dir = tmp_path / "pc-siemens"
    certificate_dir.mkdir()
    (certificate_dir / "server.cer").write_bytes(make_winrm_certificate("192.168.1.51"))
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))

    result = worker.refresh_winrm_trust_store([_winrm_test_host()])

    assert result["PC-Siemens"]["status"] == "invalid"
    assert result["PC-Siemens"]["errorCode"] == "WINRM_CERTIFICATE_HOST_MISMATCH"


def test_winrm_trust_store_rejects_ip_encoded_as_dns(tmp_path, monkeypatch):
    certificate_dir = tmp_path / "pc-siemens"
    certificate_dir.mkdir()
    (certificate_dir / "server.cer").write_bytes(make_winrm_certificate(ip_as_dns=True))
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))

    result = worker.refresh_winrm_trust_store([_winrm_test_host()])

    assert result["PC-Siemens"]["status"] == "invalid"
    assert result["PC-Siemens"]["errorCode"] == "WINRM_CERTIFICATE_HOST_MISMATCH"


def test_api_heartbeat_reports_missing_winrm_trust(client, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))
    monkeypatch.setattr(worker, "_winrm_credentials", lambda *args: ("user", "password"))
    original_hosts = worker.HOSTS
    worker.HOSTS = worker.HostRegistry({"hosts": [{
        "name": "PC-Siemens",
        "address": "192.168.1.50",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }]})
    try:
        response = client.post("/api/heartbeat/poll", json={"host": "PC-Siemens"})
    finally:
        worker.HOSTS = original_hosts

    assert response.status_code == 409
    assert response.json["code"] == "WINRM_TRUST_REQUIRED"
    assert response.json["host"] == "PC-Siemens"


def _winrm_test_host():
    return {
        "name": "PC-Siemens",
        "address": "192.168.1.50",
        "winrm_trust_ref": "pc-siemens",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }


def _install_winrm_test_host(host):
    original_hosts = worker.HOSTS
    worker.HOSTS = worker.HostRegistry({"hosts": [host]})
    return original_hosts


def _certificate_fingerprint(certificate_bytes):
    certificate = x509.load_der_x509_certificate(certificate_bytes)
    return certificate.fingerprint(hashes.SHA256()).hex().upper()


def _certificate_upload(certificate_bytes, fingerprint=None):
    data = {
        "certificate": (io.BytesIO(certificate_bytes), "winrm-server.cer"),
    }
    if fingerprint is not None:
        data["fingerprintSha256"] = fingerprint
    return data


def test_api_winrm_trust_preview_returns_metadata_without_persisting(client, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))
    original_hosts = _install_winrm_test_host(_winrm_test_host())
    certificate = make_winrm_certificate()
    try:
        response = client.post(
            "/api/hosts/PC-Siemens/winrm-trust/preview",
            data=_certificate_upload(certificate),
            content_type="multipart/form-data",
        )
    finally:
        worker.HOSTS = original_hosts

    assert response.status_code == 200
    preview = response.json["preview"]
    assert preview["status"] == "ready"
    assert preview["sanIpAddresses"] == ["192.168.1.50"]
    assert preview["fingerprintSha256"] == _certificate_fingerprint(certificate)
    assert not (tmp_path / "pc-siemens" / "server.cer").exists()


def test_api_winrm_trust_preview_rejects_host_mismatch(client, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))
    original_hosts = _install_winrm_test_host(_winrm_test_host())
    try:
        response = client.post(
            "/api/hosts/PC-Siemens/winrm-trust/preview",
            data=_certificate_upload(make_winrm_certificate("192.168.1.51")),
            content_type="multipart/form-data",
        )
    finally:
        worker.HOSTS = original_hosts

    assert response.status_code == 422
    assert response.json["code"] == "WINRM_CERTIFICATE_HOST_MISMATCH"
    assert response.json["preview"]["sanIpAddresses"] == ["192.168.1.51"]


def test_api_winrm_trust_preview_rejects_ip_encoded_as_dns(client, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))
    original_hosts = _install_winrm_test_host(_winrm_test_host())
    try:
        response = client.post(
            "/api/hosts/PC-Siemens/winrm-trust/preview",
            data=_certificate_upload(make_winrm_certificate(ip_as_dns=True)),
            content_type="multipart/form-data",
        )
    finally:
        worker.HOSTS = original_hosts

    assert response.status_code == 422
    assert response.json["code"] == "WINRM_CERTIFICATE_HOST_MISMATCH"
    assert response.json["preview"]["sanIpAddresses"] == []


def test_api_winrm_trust_save_requires_fingerprint_confirmation(client, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))
    original_hosts = _install_winrm_test_host(_winrm_test_host())
    try:
        response = client.put(
            "/api/hosts/PC-Siemens/winrm-trust",
            data=_certificate_upload(make_winrm_certificate()),
            content_type="multipart/form-data",
        )
    finally:
        worker.HOSTS = original_hosts

    assert response.status_code == 400
    assert response.json["code"] == "WINRM_FINGERPRINT_CONFIRMATION_REQUIRED"
    assert not (tmp_path / "pc-siemens" / "server.cer").exists()


def test_api_winrm_trust_save_get_and_replace_are_host_scoped(client, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))
    original_hosts = _install_winrm_test_host(_winrm_test_host())
    first_certificate = make_winrm_certificate()
    second_certificate = make_winrm_certificate()
    first_fingerprint = _certificate_fingerprint(first_certificate)
    second_fingerprint = _certificate_fingerprint(second_certificate)
    try:
        response = client.put(
            "/api/hosts/PC-Siemens/winrm-trust",
            data=_certificate_upload(first_certificate, first_fingerprint),
            content_type="multipart/form-data",
        )
        assert response.status_code == 200
        assert response.json["trust"]["fingerprintSha256"] == first_fingerprint
        assert response.json["trust"]["source"] == "lab-manager"

        certificate_path = tmp_path / "pc-siemens" / "server.cer"
        metadata_path = tmp_path / "pc-siemens" / "metadata.json"
        assert certificate_path.read_bytes() == x509.load_der_x509_certificate(first_certificate).public_bytes(
            serialization.Encoding.DER
        )
        assert json.loads(metadata_path.read_text(encoding="utf-8"))["fingerprintSha256"] == first_fingerprint

        response = client.get("/api/hosts/PC-Siemens/winrm-trust")
        assert response.status_code == 200
        assert response.json["trust"]["fingerprintSha256"] == first_fingerprint
        assert "certificate" not in response.json["trust"]

        response = client.put(
            "/api/hosts/PC-Siemens/winrm-trust",
            data=_certificate_upload(second_certificate, first_fingerprint),
            content_type="multipart/form-data",
        )
        assert response.status_code == 422
        assert response.json["code"] == "WINRM_FINGERPRINT_MISMATCH"
        assert _certificate_fingerprint(certificate_path.read_bytes()) == first_fingerprint

        response = client.put(
            "/api/hosts/PC-Siemens/winrm-trust",
            data=_certificate_upload(second_certificate, second_fingerprint),
            content_type="multipart/form-data",
        )
        assert response.status_code == 200
        assert response.json["trust"]["fingerprintSha256"] == second_fingerprint
    finally:
        worker.HOSTS = original_hosts


def test_api_winrm_trust_delete_is_idempotent_and_does_not_affect_another_host(client, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "OPS_WINRM_TRUST_PATH", str(tmp_path))
    first_host = _winrm_test_host()
    second_host = {
        **_winrm_test_host(),
        "name": "PC-Otra",
        "address": "192.168.1.51",
        "winrm_trust_ref": "pc-otra",
    }
    original_hosts = _install_winrm_test_host(first_host)
    certificate = make_winrm_certificate()
    try:
        worker.HOSTS = worker.HostRegistry({"hosts": [first_host, second_host]})
        first_path = tmp_path / "pc-siemens"
        second_path = tmp_path / "pc-otra"
        first_path.mkdir()
        second_path.mkdir()
        (first_path / "server.cer").write_bytes(certificate)
        (second_path / "server.cer").write_bytes(make_winrm_certificate("192.168.1.51"))

        response = client.delete("/api/hosts/PC-Siemens/winrm-trust")
        assert response.status_code == 200
        assert response.json["deleted"] is True
        assert not (first_path / "server.cer").exists()
        assert (second_path / "server.cer").exists()
        assert response.json["trust"]["status"] == "missing"

        response = client.delete("/api/hosts/PC-Siemens/winrm-trust")
        assert response.status_code == 200
        assert response.json["trust"]["status"] == "missing"
    finally:
        worker.HOSTS = original_hosts
