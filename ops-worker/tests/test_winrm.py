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


def make_winrm_certificate(address="192.168.1.50", *, expired=False):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    not_before = now - timedelta(days=30)
    not_after = now - timedelta(days=1) if expired else now + timedelta(days=365)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "LAB-WS-01"),
    ])
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
                x509.DNSName("LAB-WS-01"),
                x509.IPAddress(worker.ipaddress.ip_address(address)),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.DER)


def test_api_winrm_requires_host_and_command(client):
    response = client.post("/api/winrm", json={})
    assert response.status_code == 400
    assert "host and command are required" in response.get_data(as_text=True)


def test_api_winrm_rejects_unauthorized_command(client):
    response = client.post(
        "/api/winrm",
        json={"host": "lab-ws-01", "command": "not-allowed"},
    )
    assert response.status_code == 400
    assert "command 'not-allowed' not allowed" in response.get_data(as_text=True)


def test_api_winrm_returns_host_not_found(client):
    response = client.post(
        "/api/winrm",
        json={"host": "unknown", "command": "status-json"},
    )
    assert response.status_code == 404
    assert "host 'unknown' not found in config" in response.get_data(as_text=True)


@patch("worker.run_labstation_command", return_value={"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 42})
def test_api_winrm_executes_allowed_command(mock_run, client):
    original = worker.HOSTS
    worker.HOSTS = worker.HostRegistry({"hosts": [{
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "winrm_user": "user",
        "winrm_pass": "pass",
    }]})
    try:
        response = client.post(
            "/api/winrm",
            json={"host": "lab-ws-01", "command": "status-json"},
        )
    finally:
        worker.HOSTS = original

    assert response.status_code == 200
    assert response.json["exit_code"] == 0
    assert response.json["stdout"] == "ok"
    mock_run.assert_called_once()


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
