from unittest.mock import Mock

import worker


def _install_host(monkeypatch, host):
    catalog_lab_ids = [str(lab_id) for lab_id in host.get("labs", [])]
    host_config = {
        key: value
        for key, value in host.items()
        if key not in {"labs", "validLabIds"}
    }
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host_config]}))
    monkeypatch.setattr(
        worker,
        "resolve_lab_ids_for_host",
        lambda _host: list(catalog_lab_ids),
    )
    return worker.HOSTS.get(host["name"])


def test_aas_sync_route_contract_requires_host(client):
    response = client.post("/api/aas-sync", json={})

    assert response.status_code == 400
    assert response.json == {"error": "host is required"}


def test_aas_sync_route_contract_returns_not_found_for_unknown_host(client, monkeypatch):
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": []}))

    response = client.post("/api/aas-sync", json={"host": "missing"})

    assert response.status_code == 404
    assert response.json == {"error": "host 'missing' not found in config"}


def test_aas_sync_route_contract_reports_hosts_without_catalog_labs(client, monkeypatch):
    host = _install_host(monkeypatch, {"name": "lab-ws-01", "address": "192.168.1.50"})
    sync = Mock()
    monkeypatch.setattr(worker.aas_generator, "sync_lab_to_basyx", sync)

    response = client.post("/api/aas-sync", json={"host": "lab-ws-01"})

    assert response.status_code == 200
    assert response.json == {
        "host": "lab-ws-01",
        "labs": [],
        "message": "No catalog labs resolved to this host",
    }
    sync.assert_not_called()
    assert host == {"name": "lab-ws-01", "address": "192.168.1.50"}


def test_aas_sync_route_contract_forwards_each_lab_and_merges_results(client, monkeypatch):
    host = _install_host(
        monkeypatch,
        {"name": "lab-ws-01", "address": "192.168.1.50", "labs": [1, "2"]},
    )
    calls = []
    monkeypatch.setattr(
        worker.aas_generator,
        "sync_lab_to_basyx",
        lambda lab_id, host_arg: calls.append((lab_id, host_arg))
        or {"synced": True, "labId": "from-result"},
    )

    response = client.post("/api/aas-sync", json={"host": "lab-ws-01"})

    assert response.status_code == 200
    assert response.json == {
        "host": "lab-ws-01",
        "labs": [
            {"labId": "from-result", "synced": True},
            {"labId": "from-result", "synced": True},
        ],
    }
    assert calls == [("1", host), ("2", host)]


def test_aas_sync_route_contract_hides_lab_errors_and_continues(client, monkeypatch):
    host = _install_host(
        monkeypatch,
        {"name": "lab-ws-01", "address": "192.168.1.50", "labs": [1, 2]},
    )

    def sync_lab(lab_id, _host):
        if lab_id == "1":
            raise RuntimeError("secret BaSyx details")
        return {"synced": True}

    monkeypatch.setattr(worker.aas_generator, "sync_lab_to_basyx", sync_lab)

    response = client.post("/api/aas-sync", json={"host": "lab-ws-01"})

    assert response.status_code == 200
    assert response.json == {
        "host": "lab-ws-01",
        "labs": [
            {"labId": "1", "error": "AAS synchronization failed"},
            {"labId": "2", "synced": True},
        ],
    }
    assert "secret BaSyx details" not in response.get_data(as_text=True)
    assert host["name"] == "lab-ws-01"
