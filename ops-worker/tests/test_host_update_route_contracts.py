from unittest.mock import Mock

import worker


def _host_config():
    return {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "credential_ref": "lab-ws-01",
    }


def test_host_update_route_contract_rejects_non_object_payload(client, monkeypatch):
    update_host = Mock()
    monkeypatch.setattr(worker, "update_dynamic_host", update_host)

    response = client.patch("/api/hosts/lab-ws-01", json=[{"name": "invalid"}])

    assert response.status_code == 400
    assert response.json == {"error": "host update payload must be an object"}
    update_host.assert_not_called()


def test_host_update_route_contract_returns_editable_host_after_reload(client, monkeypatch):
    host_config = _host_config()
    calls = []
    monkeypatch.setattr(
        worker,
        "update_dynamic_host",
        lambda host_name, payload: calls.append((host_name, payload)) or (host_config, None),
    )
    monkeypatch.setattr(worker, "reload_hosts", lambda: (7, None))
    monkeypatch.setattr(
        worker,
        "safe_host_inventory_entry",
        lambda host, **kwargs: calls.append(("safe", host, kwargs)) or {"name": host["name"], "editable": kwargs["editable"]},
    )

    response = client.patch(
        "/api/hosts/lab-ws-01",
        json={"mac": "00-11-22-33-44-55"},
    )

    assert response.status_code == 200
    assert response.json == {
        "updated": True,
        "hosts": 7,
        "host": {"name": "lab-ws-01", "editable": True},
    }
    assert calls == [
        ("lab-ws-01", {"mac": "00-11-22-33-44-55"}),
        ("safe", host_config, {"editable": True}),
    ]


def test_host_update_route_contract_maps_catalog_conflicts_to_409(client, monkeypatch):
    reload_hosts = Mock()
    monkeypatch.setattr(
        worker,
        "update_dynamic_host",
        Mock(return_value=(None, "host is defined in the static catalog; edit manually")),
    )
    monkeypatch.setattr(worker, "reload_hosts", reload_hosts)

    response = client.patch("/api/hosts/lab-ws-01", json={"name": "renamed"})

    assert response.status_code == 409
    assert response.json == {"error": "host is defined in the static catalog; edit manually"}
    reload_hosts.assert_not_called()


def test_host_update_route_contract_maps_validation_errors_to_400(client, monkeypatch):
    reload_hosts = Mock()
    monkeypatch.setattr(
        worker,
        "update_dynamic_host",
        Mock(return_value=(None, "mac must use the supported format")),
    )
    monkeypatch.setattr(worker, "reload_hosts", reload_hosts)

    response = client.patch("/api/hosts/lab-ws-01", json={"mac": "invalid"})

    assert response.status_code == 400
    assert response.json == {"error": "mac must use the supported format"}
    reload_hosts.assert_not_called()


def test_host_update_route_contract_rejects_missing_updated_config(client, monkeypatch):
    monkeypatch.setattr(worker, "update_dynamic_host", Mock(return_value=(None, None)))
    reload_hosts = Mock()
    monkeypatch.setattr(worker, "reload_hosts", reload_hosts)

    response = client.patch("/api/hosts/lab-ws-01", json={})

    assert response.status_code == 400
    assert response.json == {"error": "host configuration could not be updated"}
    reload_hosts.assert_not_called()


def test_host_update_route_contract_maps_permission_errors_to_503(client, monkeypatch):
    monkeypatch.setattr(
        worker,
        "update_dynamic_host",
        Mock(side_effect=PermissionError("catalog path details")),
    )

    response = client.patch("/api/hosts/lab-ws-01", json={"name": "lab-ws-01"})

    assert response.status_code == 503
    assert response.json == {
        "error": "Ops host catalog is not writable; check the ops-data mount permissions",
        "code": "OPS_DYNAMIC_CONFIG_NOT_WRITABLE",
    }
    assert "catalog path details" not in response.get_data(as_text=True)


def test_host_update_route_contract_maps_read_only_oserror_to_503(client, monkeypatch):
    error = OSError("read-only filesystem details")
    error.errno = 30
    monkeypatch.setattr(worker, "update_dynamic_host", Mock(side_effect=error))

    response = client.patch("/api/hosts/lab-ws-01", json={"name": "lab-ws-01"})

    assert response.status_code == 503
    assert response.json["code"] == "OPS_DYNAMIC_CONFIG_NOT_WRITABLE"
    assert "read-only filesystem details" not in response.get_data(as_text=True)


def test_host_update_route_contract_hides_unexpected_errors(client, monkeypatch):
    error = OSError("unexpected storage secret")
    error.errno = 5
    monkeypatch.setattr(worker, "update_dynamic_host", Mock(side_effect=error))

    response = client.patch(
        "/api/hosts/lab-ws-01",
        json={"name": "lab-ws-01"},
        headers={"X-Request-ID": "host-update-1"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "host-update-1",
    }
    assert "unexpected storage secret" not in response.get_data(as_text=True)


def test_host_update_route_contract_maps_reload_failure_to_500(client, monkeypatch):
    host_config = _host_config()
    monkeypatch.setattr(worker, "update_dynamic_host", Mock(return_value=(host_config, None)))
    monkeypatch.setattr(worker, "reload_hosts", Mock(return_value=(7, "invalid catalog")))
    safe_host = Mock()
    monkeypatch.setattr(worker, "safe_host_inventory_entry", safe_host)

    response = client.patch("/api/hosts/lab-ws-01", json={"name": "lab-ws-01"})

    assert response.status_code == 500
    assert response.json == {"error": "Hosts configuration reload failed"}
    safe_host.assert_not_called()
