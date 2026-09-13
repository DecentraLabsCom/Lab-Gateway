from unittest.mock import Mock

import worker


def _install_host(monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    return host


def test_winrm_trust_preview_route_contract_returns_not_found_for_unknown_host(client, monkeypatch):
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": []}))

    response = client.post("/api/hosts/missing/winrm-trust/preview")

    assert response.status_code == 404
    assert response.json == {"error": "host 'missing' not found in config"}


def test_winrm_trust_preview_route_contract_projects_valid_pem_preview(client, monkeypatch):
    host = _install_host(monkeypatch)
    certificate = object()
    raw = b"-----BEGIN CERTIFICATE-----\nencoded\n"
    calls = []
    monkeypatch.setattr(worker, "_read_winrm_certificate_upload", lambda: raw)
    monkeypatch.setattr(worker, "_parse_winrm_certificate_bytes", lambda raw_arg: calls.append(raw_arg) or certificate)
    monkeypatch.setattr(
        worker,
        "_winrm_certificate_response_metadata",
        lambda certificate_arg, host_arg, input_format: calls.append(
            (certificate_arg, host_arg, input_format)
        ) or {"fingerprintSha256": "A" * 64, "format": input_format},
    )
    monkeypatch.setattr(worker, "_validate_winrm_certificate", lambda certificate_arg, host_arg: calls.append(("validate", certificate_arg, host_arg)))

    response = client.post(
        "/api/hosts/lab-ws-01/winrm-trust/preview",
        headers={"X-Request-ID": "trust-preview-1"},
    )

    assert response.status_code == 200
    assert response.json == {
        "requestId": "trust-preview-1",
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "preview": {"fingerprintSha256": "A" * 64, "format": "PEM", "valid": True},
    }
    assert calls == [
        raw,
        (certificate, host, "PEM"),
        ("validate", certificate, host),
    ]


def test_winrm_trust_preview_route_contract_maps_validation_error_with_preview(client, monkeypatch):
    _install_host(monkeypatch)
    monkeypatch.setattr(worker, "_read_winrm_certificate_upload", lambda: b"der")
    monkeypatch.setattr(worker, "_parse_winrm_certificate_bytes", lambda _raw: object())
    preview = {"fingerprintSha256": "B" * 64, "format": "DER"}
    monkeypatch.setattr(worker, "_winrm_certificate_response_metadata", lambda *_args: preview.copy())
    monkeypatch.setattr(
        worker,
        "_validate_winrm_certificate",
        Mock(side_effect=worker.WinRMTrustError("WINRM_CERTIFICATE_EXPIRED", "secret validation details")),
    )

    response = client.post(
        "/api/hosts/lab-ws-01/winrm-trust/preview",
        headers={"X-Request-ID": "trust-preview-2"},
    )

    assert response.status_code == 422
    assert response.json == {
        "error": worker.WINRM_CERTIFICATE_EXPIRED_MESSAGE,
        "code": "WINRM_CERTIFICATE_EXPIRED",
        "host": "lab-ws-01",
        "requestId": "trust-preview-2",
        "preview": preview,
    }
    assert "secret validation details" not in response.get_data(as_text=True)


def test_winrm_trust_preview_route_contract_maps_parse_error_without_preview(client, monkeypatch):
    _install_host(monkeypatch)
    monkeypatch.setattr(worker, "_read_winrm_certificate_upload", lambda: b"invalid")
    monkeypatch.setattr(
        worker,
        "_parse_winrm_certificate_bytes",
        Mock(side_effect=worker.WinRMTrustError("WINRM_CERTIFICATE_INVALID", "secret parser details")),
    )

    response = client.post(
        "/api/hosts/lab-ws-01/winrm-trust/preview",
        headers={"X-Request-ID": "trust-preview-3"},
    )

    assert response.status_code == 400
    assert response.json == {
        "error": worker.WINRM_CERTIFICATE_INVALID_MESSAGE,
        "code": "WINRM_CERTIFICATE_INVALID",
        "host": "lab-ws-01",
        "requestId": "trust-preview-3",
    }
    assert "preview" not in response.json
    assert "secret parser details" not in response.get_data(as_text=True)


def test_winrm_trust_preview_route_contract_hides_unexpected_errors(client, monkeypatch):
    _install_host(monkeypatch)
    monkeypatch.setattr(worker, "_read_winrm_certificate_upload", Mock(side_effect=RuntimeError("secret upload details")))

    response = client.post(
        "/api/hosts/lab-ws-01/winrm-trust/preview",
        headers={"X-Request-ID": "trust-preview-4"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "trust-preview-4",
    }
    assert "secret upload details" not in response.get_data(as_text=True)
