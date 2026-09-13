from unittest.mock import Mock

import worker


def _install_host(monkeypatch):
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "winrm_trust_ref": "pc-siemens",
    }
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    return host


def _put_payload(fingerprint="A" * 64, trust_ref="pc-siemens"):
    return {"fingerprintSha256": fingerprint, "trustRef": trust_ref}


def test_winrm_trust_mutation_contract_returns_not_found_for_put_and_delete(client, monkeypatch):
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": []}))

    put_response = client.put(
        "/api/hosts/missing/winrm-trust",
        json=_put_payload(),
    )
    delete_response = client.delete("/api/hosts/missing/winrm-trust")

    assert put_response.status_code == 404
    assert put_response.json == {"error": "host 'missing' not found in config"}
    assert delete_response.status_code == 404
    assert delete_response.json == {"error": "host 'missing' not found in config"}


def test_winrm_trust_put_contract_validates_and_stores_confirmed_certificate(client, monkeypatch):
    host = _install_host(monkeypatch)
    certificate = object()
    metadata = {"fingerprintSha256": "A" * 64, "status": "ready"}
    trust = {"configured": True, "status": "ready", **metadata}
    calls = []
    monkeypatch.setattr(worker, "_read_winrm_certificate_upload", lambda: b"certificate")
    monkeypatch.setattr(
        worker,
        "_parse_winrm_certificate_bytes",
        lambda raw: calls.append(("parse", raw)) or certificate,
    )
    monkeypatch.setattr(
        worker,
        "_validate_winrm_certificate",
        lambda received, received_host: calls.append(("validate", received, received_host)) or metadata,
    )
    monkeypatch.setattr(
        worker,
        "_store_winrm_trust_certificate",
        lambda received_host, received_certificate: calls.append(
            ("store", received_host, received_certificate)
        ) or trust,
    )

    response = client.put(
        "/api/hosts/lab-ws-01/winrm-trust",
        json=_put_payload(),
        headers={"X-Request-ID": "trust-put-1"},
    )

    assert response.status_code == 200
    assert response.json == {
        "requestId": "trust-put-1",
        "saved": True,
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "trust": trust,
    }
    assert calls == [
        ("parse", b"certificate"),
        ("validate", certificate, host),
        ("store", host, certificate),
    ]


def test_winrm_trust_put_contract_requires_fingerprint_before_upload(client, monkeypatch):
    _install_host(monkeypatch)
    read_upload = Mock()
    store_trust = Mock()
    monkeypatch.setattr(worker, "_read_winrm_certificate_upload", read_upload)
    monkeypatch.setattr(worker, "_store_winrm_trust_certificate", store_trust)

    response = client.put(
        "/api/hosts/lab-ws-01/winrm-trust",
        json={"trustRef": "pc-siemens"},
    )

    assert response.status_code == 400
    assert response.json == {
        "error": worker.WINRM_FINGERPRINT_CONFIRMATION_REQUIRED_MESSAGE,
        "code": "WINRM_FINGERPRINT_CONFIRMATION_REQUIRED",
        "host": "lab-ws-01",
        "requestId": response.json["requestId"],
    }
    read_upload.assert_not_called()
    store_trust.assert_not_called()


def test_winrm_trust_put_contract_rejects_fingerprint_mismatch_without_storage(client, monkeypatch):
    _install_host(monkeypatch)
    certificate = object()
    store_trust = Mock()
    monkeypatch.setattr(worker, "_read_winrm_certificate_upload", lambda: b"certificate")
    monkeypatch.setattr(worker, "_parse_winrm_certificate_bytes", lambda _raw: certificate)
    monkeypatch.setattr(
        worker,
        "_validate_winrm_certificate",
        lambda _certificate, _host: {"fingerprintSha256": "B" * 64},
    )
    monkeypatch.setattr(worker, "_store_winrm_trust_certificate", store_trust)

    response = client.put(
        "/api/hosts/lab-ws-01/winrm-trust",
        json=_put_payload("A" * 64),
    )

    assert response.status_code == 422
    assert response.json["code"] == "WINRM_FINGERPRINT_MISMATCH"
    assert "B" * 64 not in response.get_data(as_text=True)
    store_trust.assert_not_called()


def test_winrm_trust_put_contract_maps_storage_oserror_to_503(client, monkeypatch):
    host = _install_host(monkeypatch)
    certificate = object()
    monkeypatch.setattr(worker, "_read_winrm_certificate_upload", lambda: b"certificate")
    monkeypatch.setattr(worker, "_parse_winrm_certificate_bytes", lambda _raw: certificate)
    monkeypatch.setattr(
        worker,
        "_validate_winrm_certificate",
        lambda _certificate, _host: {"fingerprintSha256": "A" * 64},
    )
    monkeypatch.setattr(worker, "_store_winrm_trust_certificate", Mock(side_effect=OSError("secret path")))

    response = client.put(
        "/api/hosts/lab-ws-01/winrm-trust",
        json=_put_payload(),
    )

    assert response.status_code == 503
    assert response.json["code"] == "WINRM_TRUST_STORAGE_UNAVAILABLE"
    assert "secret path" not in response.get_data(as_text=True)
    assert host["name"] == response.json["host"]


def test_winrm_trust_put_contract_hides_unexpected_errors(client, monkeypatch):
    _install_host(monkeypatch)
    monkeypatch.setattr(
        worker,
        "_read_winrm_certificate_upload",
        Mock(side_effect=RuntimeError("secret certificate parser details")),
    )

    response = client.put(
        "/api/hosts/lab-ws-01/winrm-trust",
        json=_put_payload(),
        headers={"X-Request-ID": "trust-put-2"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "trust-put-2",
    }
    assert "secret certificate parser details" not in response.get_data(as_text=True)


def test_winrm_trust_delete_contract_returns_inspected_trust(client, monkeypatch):
    host = _install_host(monkeypatch)
    trust = {"configured": False, "status": "missing", "trustRef": "pc-siemens"}
    delete_trust = Mock()
    inspect_trust = Mock(return_value=trust)
    monkeypatch.setattr(worker, "_delete_winrm_trust_certificate", delete_trust)
    monkeypatch.setattr(worker, "inspect_winrm_trust", inspect_trust)

    response = client.delete(
        "/api/hosts/lab-ws-01/winrm-trust",
        headers={"X-Request-ID": "trust-delete-1"},
    )

    assert response.status_code == 200
    assert response.json == {
        "requestId": "trust-delete-1",
        "deleted": True,
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "trust": trust,
    }
    delete_trust.assert_called_once_with(host)
    inspect_trust.assert_called_once_with(host)


def test_winrm_trust_delete_contract_maps_domain_errors(client, monkeypatch):
    _install_host(monkeypatch)
    monkeypatch.setattr(
        worker,
        "_delete_winrm_trust_certificate",
        Mock(side_effect=worker.WinRMTrustError("WINRM_TRUST_INVALID", "secret trust details")),
    )

    response = client.delete("/api/hosts/lab-ws-01/winrm-trust")

    assert response.status_code == 400
    assert response.json["code"] == "WINRM_TRUST_INVALID"
    assert "secret trust details" not in response.get_data(as_text=True)


def test_winrm_trust_delete_contract_hides_unexpected_errors(client, monkeypatch):
    _install_host(monkeypatch)
    monkeypatch.setattr(
        worker,
        "_delete_winrm_trust_certificate",
        Mock(side_effect=RuntimeError("secret delete details")),
    )

    response = client.delete(
        "/api/hosts/lab-ws-01/winrm-trust",
        headers={"X-Request-ID": "trust-delete-2"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "trust-delete-2",
    }
    assert "secret delete details" not in response.get_data(as_text=True)
