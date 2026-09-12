from unittest.mock import Mock

import worker


def _install_host(monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    return host


def test_winrm_trust_get_route_contract_returns_not_found_for_unknown_host(client, monkeypatch):
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": []}))

    response = client.get("/api/hosts/missing/winrm-trust")

    assert response.status_code == 404
    assert response.json == {"error": "host 'missing' not found in config"}


def test_winrm_trust_get_route_contract_projects_inspection_with_correlation_id(client, monkeypatch):
    host = _install_host(monkeypatch)
    trust = {
        "configured": True,
        "status": "ready",
        "trustRef": "pc-siemens",
        "fingerprintSha256": "A" * 64,
    }
    calls = []
    monkeypatch.setattr(
        worker,
        "inspect_winrm_trust",
        lambda host_arg: calls.append(host_arg) or trust,
    )

    response = client.get(
        "/api/hosts/lab-ws-01/winrm-trust",
        headers={"X-Request-ID": "trust-get-1"},
    )

    assert response.status_code == 200
    assert response.json == {
        "requestId": "trust-get-1",
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "trust": trust,
    }
    assert calls == [host]


def test_winrm_trust_get_route_contract_maps_validation_error_without_details(client, monkeypatch):
    _install_host(monkeypatch)
    monkeypatch.setattr(
        worker,
        "inspect_winrm_trust",
        Mock(side_effect=worker.WinRMTrustError("WINRM_CERTIFICATE_EXPIRED", "secret parser details")),
    )

    response = client.get(
        "/api/hosts/lab-ws-01/winrm-trust",
        headers={"X-Request-ID": "trust-get-2"},
    )

    assert response.status_code == 422
    assert response.json == {
        "error": worker.WINRM_CERTIFICATE_EXPIRED_MESSAGE,
        "code": "WINRM_CERTIFICATE_EXPIRED",
        "host": "lab-ws-01",
        "requestId": "trust-get-2",
    }
    assert "secret parser details" not in response.get_data(as_text=True)


def test_winrm_trust_get_route_contract_hides_unexpected_errors(client, monkeypatch):
    _install_host(monkeypatch)
    monkeypatch.setattr(
        worker,
        "inspect_winrm_trust",
        Mock(side_effect=RuntimeError("secret trust storage details")),
    )

    response = client.get(
        "/api/hosts/lab-ws-01/winrm-trust",
        headers={"X-Request-ID": "trust-get-3"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "trust-get-3",
    }
    assert "secret trust storage details" not in response.get_data(as_text=True)
